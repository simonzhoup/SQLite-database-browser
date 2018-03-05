# -*- coding: utf-8 -*-
# Librarys
import os
import datetime
import sqlite3
import re
import collections
from collections import namedtuple, OrderedDict

from flask import Flask, render_template, request, flash, redirect, url_for, Markup

try:
    from pygments import formatters, highlight, lexers
except ImportError:
    import warnings
    warnings.warn('pygments library not found.', ImportWarning)
    syntax_highlight = lambda data: '<pre>%s</pre>' % data
else:
    def syntax_highlight(data):
        if not data:
            return ''
        lexer = lexers.get_lexer_by_name('sql')
        formatter = formatters.HtmlFormatter(linenos=False)
        return highlight(data, lexer, formatter)


# Settings
CUR_DIR = os.path.realpath(os.path.dirname(__file__))
DEBUG = True
SECRET_KEY = 'sqlite-database-browser-0.1.0'
MAX_RESULT_SIZE = 50
ROWS_PER_PAGE = 20

IndexMetadata = collections.namedtuple(
    'IndexMetadata',
    ('name', 'sql', 'columns', 'unique', 'table'))
# Variables

app = Flask(__name__)
app.config.from_object(__name__)

dataset = None

# Database Tools


class SqliteTools():

    def __init__(self, filename):
        self.file = filename
        self.db = sqlite3.connect(filename, check_same_thread=False)
        self.cursor = self.db.cursor()

    @property
    def filename(self):
        return self.file

    @property
    def location(self):
        return os.path.abspath(self.file)

    @property
    def size(self):
        return os.path.getsize(self.file)

    @property
    def created(self):
        stat = os.stat(self.file)
        return datetime.datetime.fromtimestamp(stat.st_ctime)

    @property
    def modified(self):
        stat = os.stat(self.file)
        return datetime.datetime.fromtimestamp(stat.st_mtime)

    @property
    def tables(self):
        tables = self.cursor.execute(
            'SELECT name FROM sqlite_master WHERE type="table" ORDER BY name;')
        return set([row[0] for row in tables.fetchall()])

    def get_table(self, table):
        table = self.cursor.execute(
            'SELECT * FROM %s;' % (table,)).fetchall()
        return table

    def table_sql(self, table):
        sql = self.cursor.execute('SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = ?',
                                  [table, 'table']).fetchone()[0]
        return sql

    def get_table_info(self, table):
        info = self.cursor.execute(
            "PRAGMA table_info('%s')" % table).fetchall()
        return info

    def get_foreign_keys(self, table):
        return self.cursor.execute("PRAGMA foreign_key_list('%s')" % table).fetchall()

    def get_indexes(self, table):
        return self.cursor.execute("PRAGMA index_list('%s')" % table).fetchall()

    def paginate(self, table, page, paginate_by=20, order=None):
        if page > 0:
            page -= 1
        if order:
            table_page = self.cursor.execute(
                'SELECT * FROM %s ORDER BY %s LIMIT %s OFFSET %s;' % (table, order, paginate_by, page * paginate_by)).fetchall()
        else:
            table_page = self.cursor.execute(
                'SELECT * FROM %s LIMIT %s OFFSET %s;' % (table, paginate_by, page * paginate_by)).fetchall()
        return table_page

    def drop_table(self, table):
        self.cursor.execute("DROP TABLE %s" % table)

    def copy_table(self, old_table, new_table):
        infos = self.get_table_info(old_table)
        old_columns = ','.join([row[1] for row in infos])
        if 'default' in old_columns:
            old_columns = old_columns.replace('default', '"default"')
        infos = self.get_table_info(new_table)
        new_columns = ','.join([row[1] for row in infos])
        sql = 'INSERT INTO %s(%s) SELECT %s FROM %s;' % (
            new_table, new_columns, old_columns, old_table)
        self.cursor.execute(sql)

    def drop_column(self, table, column):
        sql = self.cursor.execute('SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = ?',
                                  [table, 'table']).fetchone()[0]
        if len(re.findall('\\b' + column + '\\b', sql)) != 1:
            return False
        self.cursor.execute(
            "ALTER TABLE %s RENAME TO old_%s" % (table, table))
        sql = re.sub(column + '.+,\s+', '', sql)
        self.cursor.execute(sql)
        infos = self.get_table_info("old_%s" % table)
        old_columns = ','.join([row[1] for row in infos if row[1] != column])
        infos = self.get_table_info(table)
        new_columns = ','.join([row[1] for row in infos])
        sql = 'INSERT INTO %s(%s) SELECT %s FROM old_%s;' % (
            table, new_columns, old_columns, table)
        if 'default' in sql:
            sql = sql.replace('default', '"default"')
        self.cursor.execute(sql)
        self.drop_table("old_%s" % table)
        return True

    def add_column(self, table, column, column_type):
        columns = [row[1] for row in self.get_table_info(table)]
        if column and column not in columns and column_type:
            self.cursor.execute('ALTER TABLE %s ADD COLUMN %s %s' %
                                (table, column, column_type))
            return True
        else:
            return False

    def rename_cloumn(self, table, rename, rename_to):
        sql = self.cursor.execute('SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = ?',
                                  [table, 'table']).fetchone()[0]
        self.cursor.execute(
            "ALTER TABLE %s RENAME TO old_%s" % (table, table))
        r = '\\b' + rename + '\\b'
        sql = re.sub(r, rename_to, sql)
        self.cursor.execute(sql)
        self.copy_table("old_%s" % table, table)
        self.drop_table("old_%s" % table)

    @property
    def close(self):
        self.db.close()

    @property
    def reset(self):
        self.db.rollback()

# Views


@app.route('/', methods=('GET', 'POST'))
def index():
    return render_template('index.html')


@app.route('/<table>', methods=('GET', 'POST'))
def table_info(table):
    return render_template(
        'table_structure.html',
        columns=dataset.get_table(table),
        infos=dataset.get_table_info(table),
        table=table,
        # indexes=dataset.get_indexes(table),
        # foreign_keys=dataset.get_foreign_keys(table),
        table_sql=dataset.table_sql(table))


@app.route('/<table>/rename-column', methods=['GET', 'POST'])
def rename_column(table):
    rename = request.args.get('rename')
    infos = dataset.get_table_info(table)
    column_names = [row[1] for row in infos]
    if request.method == 'POST':
        new_name = request.form.get('rename_to', '')
        rename = request.form.get('rename', '')
        if new_name and new_name not in column_names:
            dataset.rename_cloumn(table, rename, new_name)
            flash('Column "%s" was renamed successfully!' % rename, 'success')
        else:
            flash('Column name is required and cannot conflict with an '
                  'existing column\'s name.', 'danger')
        return redirect(url_for('rename_column', table=table))
    return render_template(
        'rename_column.html',
        infos=infos,
        table=table,
        rename=rename,
    )


@app.route('/<table>/drop-column/', methods=['GET', 'POST'])
def drop_column(table):
    name = request.args.get('name')
    infos = dataset.get_table_info(table)
    if request.method == 'POST':
        column_names = [row[1] for row in infos]
        name = request.form.get('name', '')
        if name and name in column_names:
            if dataset.drop_column(table, name):
                flash('Column "%s" was dropped successfully!' %
                      name, 'success')
            else:
                flash('Drop column is unsuccessful', 'danger')
        else:
            flash('Name is required.', 'danger')
        return redirect(url_for('drop_column', table=table))

    return render_template(
        'drop_column.html',
        infos=infos,
        table=table,
        name=name)


@app.route('/<table>/add-column/', methods=['GET', 'POST'])
def add_column(table):
    column_mapping = ['VARCHAR', 'TEXT', 'INTEGER', 'REAL',
                      'BOOL', 'BLOB', 'DATETIME', 'DATE', 'TIME', 'DECIMAL']
    if request.method == 'POST':
        name = request.form.get('name', '')
        column_type = request.form.get('type', '')
        if name and column_type and dataset.add_column(table, name, column_type):
            flash('Column "%s" creatr success' % name, 'success')
        else:
            flash(
                'Please check that table has already existed, Type is not empty', 'danger')
        return redirect(url_for(add_column), table=table)
    return render_template(
        'add_column.html',
        column_mapping=column_mapping,
        table=table)


@app.route('/<table>/content/', methods=['GET', 'POST'])
def table_content(table):
    # filter
    columns_count = dataset.get_table(table)
    ordering = request.args.get('ordering')
    rows_per_page = app.config['ROWS_PER_PAGE']
    page = request.args.get('page', 1, type=int)
    if ordering:
        columns = dataset.paginate(
            table, page, paginate_by=rows_per_page, order=ordering)
    else:
        columns = dataset.paginate(
            table=table, page=page, paginate_by=rows_per_page)
    total_pages = len(columns_count) // rows_per_page
    previous_page = page - 1
    next_page = page + 1 if page + \
        1 <= total_pages else 0
    print(next_page)
    return render_template(
        'table_content.html',
        columns=columns,
        ordering=ordering,
        page=page,
        total_pages=total_pages,
        previous_page=previous_page,
        next_page=next_page,
        columns_count=columns_count,
        infos=dataset.get_table_info(table),
        table=table,
    )


@app.route('/<table>/query/', methods=['GET', 'POST'])
def table_query(table):
    row_count, error, data, data_description = None, None, None, None
    if request.method == 'POST':
        sql = request.form.get('sql', '')
        if 'export_json' in request.form:
            return export(table, sql, 'json')
        elif 'export_csv' in request.form:
            return export(table, sql, 'csv')
        try:
            cur = dataset.cursor.execute(sql)
            dataset.db.commit()
        except Exception as exc:
            error = str(exc)
        else:
            data = cur.fetchall()[:app.config['MAX_RESULT_SIZE']]
            data_description = cur.description
            row_count = cur.rowcount
    else:
        if request.args.get('sql'):
            sql = request.args.get('sql')
        else:
            sql = 'SELECT *\nFROM "%s"' % (table)

    return render_template(
        'table_query.html',
        row_count=row_count,
        data=data,
        data_description=data_description,
        table=table,
        sql=sql,
        query_images=get_query_images(),
        error=error,
        table_sql=dataset.table_sql(table)
    )


@app.route('/table-definition/', methods=['POST'])
def set_table_definition_preference():
    key = "show"
    show = False
    if request.form.get(key):
        session[key] = show = True
    elif key in request.session:
        del request.session[key]
    return jsonify({key: show})


@app.template_filter()
def format_create_table(sql):
    try:
        return _format_create_table(sql)
    except:
        return sql


@app.template_filter('highlight')
def highlight_filter(data):
    return Markup(syntax_highlight(data))


def get_query_images():
    accum = []
    image_dir = os.path.join(app.static_folder, 'img')
    if not os.path.exists(image_dir):
        return accum
    for filename in sorted(os.listdir(image_dir)):
        basename = os.path.splitext(os.path.basename(filename))[0]
        parts = basename.split('-')
        accum.append((parts, 'img/' + filename))
    return accum


def export(table, sql, export_format):
    cur = dataset.cursor.execute(sql)
    data = cur.fetchall()
    data_description = cur.description
    row_count = cur.rowcount
    for col_desc in data_description:
        print(col_desc[0])
    for row in data:
        print(row)


@app.context_processor
def _general():
    return {
        'dataset': dataset,
    }


@app.before_request
def _before_request():
    global dataset
    dataset = SqliteTools(database)


@app.teardown_request
def _reset_db(e):
    dataset.reset
    dataset.close


def main():
    global database
    database = 'data-dev.sqlite'
    app.run()

# Run
if __name__ == '__main__':
    main()

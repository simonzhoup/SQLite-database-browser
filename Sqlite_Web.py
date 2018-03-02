# -*- coding: utf-8 -*-
# Librarys
import os
import datetime
import sqlite3
import collections

from flask import Flask, render_template, request, flash, redirect, url_for


# Settings
CUR_DIR = os.path.realpath(os.path.dirname(__file__))
DEBUG = True
SECRET_KEY = 'sqlite-database-browser-0.1.0'
MAX_RESULT_SIZE = 1000
ROWS_PER_PAGE = 20

IndexMetadata = collections.namedtuple(
    'IndexMetadata',
    ('name', 'sql', 'columns', 'unique', 'table'))
# Variables

app = Flask(__name__)
app.config.from_object(__name__)

dataset = None

# Database Tools
property


class SqliteTools():

    def __init__(self, filename):
        self.filename = filename
        self.db = sqlite3.connect(filename, check_same_thread=False)
        self.cursor = self.db.cursor()

    @property
    def filename(self):
        return os.path.realpath(self.filename)

    @property
    def location(self):
        return os.path.abspath(self.filename)

    @property
    def size(self):
        return os.path.getsize(self.filename)

    @property
    def created(self):
        stat = os.stat(self.filename)
        return datetime.datetime.fromtimestamp(stat.st_ctime)

    @property
    def modified(self):
        stat = os.stat(self.filename)
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

    def drop_column(self, table):
        self.cursor.execute("DROP TABLE %s" % table)

    def rename_cloumn(self, table, rename, rename_to):
        sql = self.cursor.execute('SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = ?',
                                  [table, 'table']).fetchone()[0]
        self.cursor.execute(
            "ALTER TABLE %s RENAME TO old_%s" % (table, table))
        sql = sql.replace(rename, rename_to)
        self.cursor.execute(sql)
        self.drop_column("old_%s" % table)

    @property
    def close(self):
        self.db.close()
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
        indexes=dataset.get_indexes(table),
        foreign_keys=dataset.get_foreign_keys(table),
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
def _close_db(e):
    dataset.close


def main():
    global database
    database = 'data-dev.sqlite'
    app.run()

# Run
if __name__ == '__main__':
    main()

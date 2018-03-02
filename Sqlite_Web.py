# -*- coding: utf-8 -*-
# Librarys
import os
import datetime
import sqlite3
import collections

from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy


# Settings
CUR_DIR = os.path.realpath(os.path.dirname(__file__))
DEBUG = True
SECRET_KEY = 'sqlite-database-browser-0.1.0'
SQLALCHEMY_TRACK_MODIFICATIONS = True
SQLALCHEMY_DATABASE_URI = "sqlite:////data-dev.sqlite"
MAX_RESULT_SIZE = 1000
ROWS_PER_PAGE = 50

IndexMetadata = collections.namedtuple(
    'IndexMetadata',
    ('name', 'sql', 'columns', 'unique', 'table'))
# Variables

app = Flask(__name__)
app.config.from_object(__name__)

db = SQLAlchemy()
db.init_app(app)
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

    def get_table(self, table, order='id'):
        table = self.cursor.execute(
            'SELECT * FROM %s ORDER BY %s;' % (table, order)).fetchall()
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


@app.route('/<table>/content/', methods=['GET', 'POST'])
def table_content(table):
    return render_template(
        'table_content.html',
        columns=dataset.get_table(table),
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

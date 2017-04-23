import unittest
from os.path import abspath, dirname, join, basename
from subprocess import Popen
from tempfile import NamedTemporaryFile

from time import sleep

import os
from unittest.case import skipIf

import requests
import sys

from requests.exceptions import ConnectionError
from requests.models import Response

import eventsourcing
from eventsourcing.example import flaskapp
from eventsourcing.infrastructure.sqlalchemy.datastore import SQLAlchemyDatastore, SQLAlchemySettings

path_to_virtualenv = None
if hasattr(sys, 'real_prefix'):
    path_to_virtualenv = sys.prefix

path_to_eventsourcing = dirname(dirname(abspath(eventsourcing.__file__)))
path_to_flaskapp = abspath(flaskapp.__file__)
path_to_flaskwsgi = join(dirname(path_to_flaskapp), 'flaskwsgi.py')


class TestFlaskApp(unittest.TestCase):
    port = 5001

    def setUp(self):
        super(TestFlaskApp, self).setUp()
        self.app = self.start_app()

    def start_app(self):
        cmd = [sys.executable, path_to_flaskapp]
        return Popen(cmd)

    def tearDown(self):
        self.app.terminate()
        sleep(1)
        self.app.kill()
        sleep(1)
        self.app.wait()
        super(TestFlaskApp, self).tearDown()

    def test(self):
        max_retries = 100
        while max_retries:
            try:
                response = requests.get('http://localhost:{}'.format(self.port))
            except ConnectionError:
                sleep(0.1)
                max_retries -= 1
            else:
                self.assertIsInstance(response, Response)
                self.assertIn('Hello There!', response.text)
                break
        else:
            self.fail("Couldn't get response from app")


@skipIf('pypy' in basename(sys.executable), 'uwsgi needs special plugin for pypy')
class TestFlaskWsgi(TestFlaskApp):
    port = 9001

    def start_app(self):
        # Make up a DB URI.
        self.tempfile = NamedTemporaryFile()
        uri = 'sqlite:///{}'.format(self.tempfile.name)

        # Setup tables.
        datastore = SQLAlchemyDatastore(
            settings=SQLAlchemySettings(uri=uri),
        )
        datastore.setup_connection()
        datastore.setup_tables()
        datastore.drop_connection()

        # Run uwsgi.
        path_to_uwsgi = join(path_to_virtualenv, 'bin', 'uwsgi')
        assert os.path.exists(path_to_uwsgi), path_to_uwsgi
        cmd = [path_to_uwsgi]
        # if path_to_virtualenv is not None:
        #     cmd += ['-H', path_to_virtualenv]
        cmd += ['--master']
        cmd += ['--processes', '4']
        cmd += ['--threads', '2']
        cmd += ['--wsgi-file', path_to_flaskwsgi]
        cmd += ['--http', ':{}'.format(self.port)]
        return Popen(cmd, env={
            'PYTHONPATH': ':'.join(os.getenv('PYTHONPATH', '').split(':') + [path_to_eventsourcing]),
            'DB_URI': uri
        })

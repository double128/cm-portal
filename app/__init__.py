#!/usr/bin/python3
from flask import Flask, session, jsonify
from config import Config
from flask_login import LoginManager
from celery import Celery
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_marshmallow import Marshmallow
from flask_bootstrap import Bootstrap

app = Flask(__name__)
app.config.from_object(Config)
#sqlalchemy_exc = exc
session = Session(app)
login = LoginManager(app)
login.login_view = 'login'
login.users = {}
csrf = CSRFProtect(app)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
db = SQLAlchemy(app)
migrate = Migrate(app, db)
ma = Marshmallow(app)
bootstrap = Bootstrap(app)
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'], backend=app.config['CELERY_BACKEND_URL'])
celery.conf.update(app.config)

from app import routes, db_model

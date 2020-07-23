from flask import Flask
from redis import Redis
import rq
from retrobiocat_web.config import Config
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from flask_jsglue import JSGlue
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_security import Security, MongoEngineUserDatastore, hash_password
from flask_mail import Mail
from flask_admin import Admin
from flask_session import Session
from flask_mongoengine import MongoEngine
import datetime
from mongoengine import disconnect

csrf = CSRFProtect()
jsglue = JSGlue()
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute", "1800/hour"])
talisman = Talisman(content_security_policy=False)
mail = Mail()
admin_ext = Admin()
db = MongoEngine()
session = Session()

from retrobiocat_web.mongo.models.user_models import User, Role
from retrobiocat_web.app.user_model_forms import ExtendedConfirmRegisterForm, ExtendedRegisterForm

from retrobiocat_web.mongo.models.biocatdb_models import EnzymeType, Sequence, Paper, Molecule, Activity
from retrobiocat_web.app.admin import MyAdminIndexView, MyModelView

user_datastore = MongoEngineUserDatastore(db, User, Role)

from retrobiocat_web.app import main_site, retrobiocat, biocatdb, contributions

def quick_db(config_class=Config):
    print("Make a quick app to init mongoengine..")
    app = Flask(__name__)
    app.config.from_object(config_class)
    disconnect()
    db.init_app(app)
    print('..done')
    return app

def create_app(config_class=Config, use_talisman=True):
    print("Create app...")
    app = Flask(__name__)
    app.config.from_object(config_class)

    print("Init task queues...")
    app.redis = Redis.from_url(app.config['REDIS_URL'])
    app.task_queue = rq.Queue('tasks', connection=app.redis, default_timeout=600)
    app.network_queue = rq.Queue('network', connection=app.redis, default_timeout=600)
    app.pathway_queue = rq.Queue('pathway', connection=app.redis, default_timeout=600)
    app.retrorules_queue = rq.Queue('retrorules', connection=app.redis, default_timeout=600)
    app.db_queue = rq.Queue('db', connection=app.redis, default_timeout=2400)

    print("Init addons...")
    if use_talisman == True:
        talisman.init_app(app, content_security_policy=False)

    csrf.init_app(app)
    disconnect()
    db.init_app(app)
    jsglue.init_app(app)
    session.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    security = Security(app, user_datastore,
                        confirm_register_form=ExtendedConfirmRegisterForm,
                        register_form=ExtendedRegisterForm)

    print("Prepare admin views..")
    admin_ext.init_app(app, index_view=MyAdminIndexView())
    admin_ext.add_view(MyModelView(User))
    admin_ext.add_view(MyModelView(Role))
    admin_ext.add_view(MyModelView(EnzymeType))
    admin_ext.add_view(MyModelView(Sequence))
    admin_ext.add_view(MyModelView(Paper))
    admin_ext.add_view(MyModelView(Molecule))
    admin_ext.add_view(MyModelView(Activity))

    # Create a user to test with
    @app.before_first_request
    def create_user():
        admin = user_datastore.find_or_create_role('admin', description='admin role')
        user_datastore.find_or_create_role('enzyme_types_admin', description='enzyme_types_admin')
        user_datastore.find_or_create_role('contributor', description='contributor')
        user_datastore.find_or_create_role('rxn_rules_admin', description='rxn_rules_admin')
        user_datastore.find_or_create_role('experimental', description='experimental')

        if not user_datastore.get_user(app.config['ADMIN_EMAIL']):
            user = user_datastore.create_user(email=app.config['ADMIN_EMAIL'],
                                              password=hash_password(app.config['ADMIN_PASSWORD']),
                                              first_name='Admin',
                                              last_name='',
                                              affiliation='RetroBioCat',
                                              confirmed_at=datetime.datetime.now())
            user_datastore.add_role_to_user(user, admin)
        print("done")

    @app.context_processor
    def inject_login_mode():
        login_mode = app.config['USE_EMAIL_CONFIRMATION']
        return dict(login_mode=login_mode)

    print("Register blueprints...")
    with app.app_context():
        app.register_blueprint(main_site.bp)
        app.register_blueprint(retrobiocat.bp)
        app.register_blueprint(biocatdb.bp)
        app.register_blueprint(contributions.bp)

        return app









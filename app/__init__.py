from datetime import timedelta

from flask import Flask
from flask_caching import Cache
from flask_login import LoginManager

app = Flask(__name__)
app.secret_key = 'some secret salt'
app.jinja_env.add_extension('jinja2.ext.do')
app.jinja_env.add_extension('jinja2.ext.loopcontrols')

cache = Cache(config={'CACHE_TYPE': 'SimpleCache', "CACHE_DEFAULT_TIMEOUT": 3000})
cache.init_app(app)
login_manager = LoginManager(app)

app.config['SITEMAP_INCLUDE_RULES_WITHOUT_PARAMS'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=3)

from app.routes.add import bp as add_bp
app.register_blueprint(add_bp, url_prefix='/add')

from app.routes.service import bp as service_bp
app.register_blueprint(service_bp, url_prefix='/service')

from app.routes.config import bp as config_bp
app.register_blueprint(config_bp, url_prefix='/config')

from app.routes.metric import bp as metric_bp
app.register_blueprint(metric_bp, url_prefix='/metrics')

from app.routes.waf import bp as waf_bp
app.register_blueprint(waf_bp, url_prefix='/waf')

from app.routes.runtime import bp as runtime_bp
app.register_blueprint(runtime_bp, url_prefix='/runtimeapi')

from app.routes.smon import bp as smon_bp
app.register_blueprint(smon_bp, url_prefix='/smon')

from app.routes.checker import bp as checker_bp
app.register_blueprint(checker_bp, url_prefix='/checker')

from app.routes.install import bp as install_bp
app.register_blueprint(install_bp, url_prefix='/install')

from app.routes.user import bp as user_bp
app.register_blueprint(user_bp, url_prefix='/user')

from app.routes.server import bp as server_bp
app.register_blueprint(server_bp, url_prefix='/server')

from app.routes.admin import bp as admin_bp
app.register_blueprint(admin_bp, url_prefix='/admin')

from app import views
from app import ajax_views

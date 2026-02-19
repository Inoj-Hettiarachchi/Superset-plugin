"""
Data Entry Plugin for Apache Superset
Adds dynamic form management capabilities to Superset
"""
from flask import Flask, Blueprint
from flask_appbuilder import AppBuilder
from sqlalchemy import create_engine, text
import logging
import os

logger = logging.getLogger(__name__)

__version__ = '1.0.0'

# Get plugin directory for template loading
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FOLDER = os.path.join(PLUGIN_DIR, 'templates')
STATIC_FOLDER = os.path.join(PLUGIN_DIR, 'static')


class SupersetDataEntryPlugin:
    """
    Plugin that registers itself with Superset's AppBuilder
    Adds custom views and API endpoints for data entry forms
    """
    
    def __init__(self, appbuilder: AppBuilder):
        """
        Initialize and register the plugin
        
        Args:
            appbuilder: Superset's AppBuilder instance
        """
        self.appbuilder = appbuilder
        self.app = appbuilder.app
        
        # Setup with error boundaries
        try:
            self._setup_template_folder()
            self._setup_static_files()
            self._setup_database()
            self._register_views()
            self._register_api()
            self._health_check()
            logger.info("✅ Data Entry Plugin loaded successfully")
        except Exception as e:
            logger.error(f"❌ Plugin initialization failed: {e}")
            raise
    
    def _setup_template_folder(self):
        """
        Configure Flask to find plugin templates
        """
        from jinja2 import ChoiceLoader, FileSystemLoader
        
        # Add plugin template folder to Jinja2 loader
        plugin_loader = FileSystemLoader(TEMPLATE_FOLDER)
        
        # Get existing loaders
        existing_loader = self.app.jinja_loader
        
        # Create a choice loader that checks plugin templates first, then falls back to existing
        self.app.jinja_loader = ChoiceLoader([plugin_loader, existing_loader])
        
        logger.info(f"✅ Plugin templates configured at: {TEMPLATE_FOLDER}")
    
    def _setup_static_files(self):
        """
        Register a Flask Blueprint to serve plugin static files (JS, CSS).
        This avoids inline scripts which are blocked by Superset's CSP.
        """
        static_bp = Blueprint(
            'data_entry_static',
            __name__,
            static_folder=STATIC_FOLDER,
            static_url_path='/static'
        )
        self.app.register_blueprint(static_bp, url_prefix='/data-entry-plugin')
        logger.info(f"✅ Plugin static files registered at: /data-entry-plugin/static/")
    
    def _setup_database(self):
        """
        Configure connection to application database
        """
        db_config = self.app.config.get('DATA_ENTRY_DB_CONFIG')
        
        if not db_config:
            raise ValueError("DATA_ENTRY_DB_CONFIG not found in Superset configuration")
        
        if not all(db_config.values()):
            raise ValueError("DATA_ENTRY_DB_CONFIG has missing values")
        
        # Create SQLAlchemy engine URI for application database
        uri = (
            f"postgresql://{db_config['username']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        )
        
        # Store URI and create a shared engine (engines are heavyweight and manage
        # connection pools -- they must be created once, not per-request)
        self.app.config['DATA_ENTRY_DB_URI'] = uri
        self.app.config['DATA_ENTRY_ENGINE'] = create_engine(uri, pool_pre_ping=True)
        
        logger.info(f"✅ Plugin connected to database: {db_config['database']}")
    
    def _register_views(self):
        """
        Register all plugin views with Superset's menu
        """
        from .views import (
            FormListView,
            FormBuilderView,
            DataEntryView,
            DataGridView
        )
        
        # Add main form list view
        self.appbuilder.add_view(
            FormListView,
            "data_entry_forms",
            label="Data Entry Forms",
            icon="fa-wpforms",
            category="Data Entry",
            category_icon="fa-database",
        )
        
        # Add form builder view (admin only)
        self.appbuilder.add_view(
            FormBuilderView,
            "form_builder",
            label="Configure Forms",
            icon="fa-cogs",
            category="Data Entry",
        )
        
        # Register data entry and grid views (not in menu, but accessible via routes)
        self.appbuilder.add_view_no_menu(DataEntryView)
        self.appbuilder.add_view_no_menu(DataGridView)
        
        logger.info("✅ Plugin views registered in Superset menu")
    
    def _register_api(self):
        """
        Register API blueprint with Flask app
        """
        from .api import data_entry_api_bp
        
        self.app.register_blueprint(
            data_entry_api_bp,
            url_prefix='/api/v1/data-entry'
        )
        
        logger.info("✅ Plugin API registered at /api/v1/data-entry")
    
    def _health_check(self):
        """
        Verify plugin is working correctly
        Checks database connectivity and table existence
        """
        try:
            engine = self.app.config['DATA_ENTRY_ENGINE']
            
            with engine.connect() as conn:
                # Check if plugin tables exist
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name IN ('form_configurations', 'form_fields')
                """))
                count = result.scalar()
                
                if count == 2:
                    logger.info("✅ Plugin database tables found")
                else:
                    logger.warning(
                        "⚠️  Plugin tables not found. "
                        "Run database migrations (V6, V7) to create required tables."
                    )
                
        except Exception as e:
            logger.error(f"❌ Plugin health check failed: {e}")
            raise


def register_plugin(appbuilder: AppBuilder):
    """
    Entry point for plugin registration
    Called by Superset during initialization via FLASK_APP_MUTATOR
    
    Args:
        appbuilder: Superset's AppBuilder instance
    
    Returns:
        SupersetDataEntryPlugin instance
    
    Example:
        # In superset_config.py
        def FLASK_APP_MUTATOR(app):
            from superset_data_entry import register_plugin
            register_plugin(app.appbuilder)
    """
    return SupersetDataEntryPlugin(appbuilder)

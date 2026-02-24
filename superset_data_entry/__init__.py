"""
Data Entry Plugin for Apache Superset
Adds dynamic form management capabilities to Superset
"""
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
    
    def __init__(self, appbuilder):
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
        from flask import Blueprint
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
        Configure connection to Superset's database
        Uses SQLALCHEMY_DATABASE_URI from Superset configuration
        """
        try:
            from sqlalchemy import create_engine
            # Verify import succeeded
            if create_engine is None:
                raise ImportError("create_engine is None after import. SQLAlchemy may be corrupted.")
        except ImportError as e:
            raise ImportError(
                f"SQLAlchemy not available: {e}. "
                "Ensure SQLAlchemy is installed in Superset's environment."
            )
        except NameError as e:
            raise ImportError(
                f"Failed to import create_engine from sqlalchemy: {e}. "
                "This may indicate a SQLAlchemy version compatibility issue."
            )

        # Get Superset's database URI
        uri = self.app.config.get('SQLALCHEMY_DATABASE_URI')
        
        if not uri:
            raise ValueError("SQLALCHEMY_DATABASE_URI not found in Superset configuration")
        
        # Store URI and create a shared engine (engines are heavyweight and manage
        # connection pools -- they must be created once, not per-request)
        self.app.config['DATA_ENTRY_DB_URI'] = uri
        self.app.config['DATA_ENTRY_ENGINE'] = create_engine(uri, pool_pre_ping=True)
        
        logger.info("✅ Plugin connected to Superset's database")
    
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
    
    def _run_migrations_if_needed(self):
        """Run bundled migrations if plugin tables or columns are missing."""
        try:
            from sqlalchemy import text
        except ImportError as e:
            raise ImportError(
                f"SQLAlchemy not available: {e}. "
                "Ensure SQLAlchemy is installed in Superset's environment."
            )
        engine = self.app.config['DATA_ENTRY_ENGINE']
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('form_configurations', 'form_fields')
            """))
            count = result.scalar()
        run_needed = count < 2
        if not run_needed:
            # Check if form_configurations has allowed_role_names (V8)
            with engine.connect() as conn:
                r = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'form_configurations'
                    AND column_name = 'allowed_role_names'
                """))
                run_needed = r.scalar() == 0
        if run_needed:
            from .migrations_runner import run_migrations
            logger.info("Plugin migrations needed; running...")
            run_migrations(engine)
            logger.info("✅ Migrations completed")
        else:
            logger.info("✅ Plugin database tables found")
    
    def _health_check(self):
        """
        Verify plugin is working correctly
        Checks database connectivity and table existence
        """
        try:
            engine = self.app.config['DATA_ENTRY_ENGINE']
            self._run_migrations_if_needed()
        except Exception as e:
            logger.error(f"❌ Plugin health check failed: {e}")
            raise


def register_plugin(appbuilder):
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
    # Lazy import to avoid requiring Flask/AppBuilder at module import time (for setup_cli)
    from flask_appbuilder import AppBuilder
    if not isinstance(appbuilder, AppBuilder):
        raise TypeError("appbuilder must be an AppBuilder instance")
    return SupersetDataEntryPlugin(appbuilder)

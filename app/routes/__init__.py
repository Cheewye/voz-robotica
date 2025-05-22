from flask import Flask
from flask_cors import CORS
from app.routes.main import main_routes
import os

def create_app():
    # Define la ruta absoluta a app/templates/
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    app = Flask(__name__, template_folder=template_dir)
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

    # Registra el blueprint
    app.register_blueprint(main_routes)

    return app
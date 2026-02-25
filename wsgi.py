"""WSGI entrypoint for PythonAnywhere."""

from trainer.webapp import create_app

application = create_app()

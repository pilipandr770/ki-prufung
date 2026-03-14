import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .builder import ReportContext

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


class ReportRenderer:
    def __init__(self):
        self._env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=select_autoescape(["html"]),
        )

    def render_html(self, ctx: ReportContext) -> str:
        template = self._env.get_template("report.html.j2")
        return template.render(ctx=ctx)

    def render_pdf(self, html: str) -> bytes | None:
        import contextlib, io
        buf = io.StringIO()
        try:
            # redirect_stderr suppresses WeasyPrint's GTK-not-found messages on Windows
            with contextlib.redirect_stderr(buf):
                from weasyprint import HTML
                return HTML(string=html, base_url=TEMPLATE_DIR).write_pdf()
        except Exception:
            return None

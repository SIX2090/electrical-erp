"""Help routes: in-app operation manual and AI guidance pages."""
from flask import jsonify, render_template, request

from services.erp_help_service import ERP_OPERATION_MANUAL, build_ai_guidance


def register_routes(app, deps):
    login_required = deps["login_required"]

    @app.get("/help/operation-manual", endpoint="help_operation_manual")
    @login_required
    def operation_manual():
        return render_template("operation_manual.html", manual_sections=ERP_OPERATION_MANUAL)

    @app.get("/help/assistant", endpoint="help_operation_assistant")
    @login_required
    def operation_assistant():
        return render_template("ai_assistant.html")

    @app.post("/api/ai-assistant/help", endpoint="help_ai_assistant_api")
    @login_required
    def ai_assistant_help_api():
        payload = request.get_json(silent=True) or {}
        question = (payload.get("question") or "").strip()
        mode = (payload.get("mode") or "operation").strip() or "operation"
        if not question:
            return jsonify({"msg": "Question is required."}), 400
        return jsonify(build_ai_guidance(question, mode=mode))

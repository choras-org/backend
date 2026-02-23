from flask.views import MethodView
from flask_smorest import Blueprint
from flask import request
import os

blp = Blueprint("Receive", __name__, description="Receive simulation backend files API")

@blp.route("/receive")
class ReceiveObject(MethodView):

    def post(self):
        if "file" not in request.files:
            return {"error": "No file part"}, 400

        file = request.files["file"]

        try:
            # Process file here (this is synchronous)
            # Get path to project root (one level above this routes folder)
            print("WE ARE IN THE RECEIVE API ENDPOINT AT BACKEND")
            project_root = os.path.dirname(os.path.dirname(__file__))

            # Ensure output folder exists
            output_dir = os.path.join(project_root, "output")
            os.makedirs(output_dir, exist_ok=True)

            # Always use "output.json" as filename
            output_path = os.path.join(output_dir, "output.json")

            # Save the uploaded file
            file.save(output_path)

            print(f"File saved to {output_path}")

        except Exception as e:
            return {"error": str(e)}, 500

        return {"status": "processed"}, 200

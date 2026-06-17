from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.user_preference_schema import (
  UserPreferenceSchema,
  UserPreferenceUpdateBodySchema,
)
from app.services import user_preference_service

blp = Blueprint("User Preference", __name__, description="User Preference API")

@blp.route("/user-preferences")
class UserPreference(MethodView):
    @blp.response(200, UserPreferenceSchema(many=True))
    def get(self):
        return user_preference_service.get_all_user_preferences()
    
@blp.route("/user-preferences/<int:user_preference_id>")
class UserPreferenceDetail(MethodView):
    @blp.arguments(UserPreferenceUpdateBodySchema)
    @blp.response(200, UserPreferenceSchema)
    def put(self, body_data, user_preference_id):
        result = user_preference_service.update_user_preference(user_preference_id, body_data)
        return result

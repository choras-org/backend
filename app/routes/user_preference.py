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
    """
    HTTP methods for handling collections of user preferences.
    """

    @blp.response(200, UserPreferenceSchema(many=True))
    def get(self):
        """
        Retrieve a list of all user preferences.

        Returns
        -------
        list of UserPreference
            A list of user preference database objects matching the schema.
        """
        return user_preference_service.get_all_user_preferences()
    
@blp.route("/user-preferences/<int:user_preference_id>")
class UserPreferenceDetail(MethodView):
    """
    HTTP methods for handling operations on specific user preference records.
    """

    @blp.arguments(UserPreferenceUpdateBodySchema)
    @blp.response(200, UserPreferenceSchema)
    def put(self, body_data, user_preference_id):
        """
        Update an existing user preference configuration by its unique ID.

        Parameters
        ----------
        body_data : dict
            The validated request body containing updated user preference data.
        user_preference_id : int
            The unique identifier of the user preference record to modify.

        Returns
        -------
        UserPreference
            The updated user preference database object matching the schema.
        """
        result = user_preference_service.update_user_preference(user_preference_id, body_data)
        return result
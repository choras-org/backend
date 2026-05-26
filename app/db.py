import sqlalchemy
from alembic import op
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade():
    with op.batch_alter_table("test", schema=None, naming_convention=naming_convention) as batch_op:
        batch_op.drop_constraint("fk_test_user_id_user", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_test_user_id_user"),
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )


metadata = MetaData(naming_convention=naming_convention)

db: sqlalchemy = SQLAlchemy()

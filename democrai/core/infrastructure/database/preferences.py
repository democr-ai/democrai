from typing import Any
from sqlalchemy.exc import OperationalError
from democrai.core.infrastructure.database import session_scope
from democrai.core.infrastructure.database.models import Preference


def get_preference(key: str, default: Any = None) -> Any:
    """
    Retrieves a preference value from democrai.db.
    """
    try:
        with session_scope() as session:
            pref = session.query(Preference).filter(Preference.key == key).first()
            if pref:
                return pref.value
            return default
    except OperationalError:
        return default


def set_preference(key: str, value: str) -> None:
    """
    Sets a preference value in democrai.db.
    """
    try:
        with session_scope() as session:
            pref = session.query(Preference).filter(Preference.key == key).first()
            if pref:
                pref.value = value
            else:
                pref = Preference(key=key, value=value)
                session.add(pref)
            session.commit()
    except OperationalError:
        return

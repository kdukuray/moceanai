from models import *
import db

def create_profile(**kwargs):
    with db.sessionLocal() as session:
        new_profile = Profile(**kwargs)
        session.add(new_profile)
        session.commit()
        session.refresh(new_profile)
        return new_profile


def update_profile(profile_id, **kwargs):
    with db.sessionLocal() as session:
        profile_to_be_updated = session.get(Profile, profile_id)
        if not profile_to_be_updated:
            return None
        for key, value in kwargs.items():
            setattr(profile_to_be_updated, key, value)
        session.commit()
        session.refresh(profile_to_be_updated)
        return profile_to_be_updated

def delete_profile(profile_id):
    with db.sessionLocal() as session:
        profile_be_deleted = session.get(Profile, profile_id)
        if not profile_be_deleted:
            return False
        session.delete(profile_be_deleted)
        session.commit()
        return True

def get_profile(profile_id):
    with db.sessionLocal() as session:
        target_profile = session.get(Profile, profile_id)
        if not target_profile:
            return None
        return target_profile

def get_all_profiles():
    with db.sessionLocal() as session:
        return session.query(Profile).all()
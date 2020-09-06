import mongoengine as db
from retrobiocat_web.mongo.models.user_models import User
from datetime import datetime
import uuid
from bson import ObjectId

class Reaction(db.Document):
    name = db.StringField(unique=True)
    smarts = db.ListField(db.StringField())
    enzyme_types = db.ListField(db.StringField())
    cofactors = db.DictField()
    positive_tests = db.ListField(db.StringField())
    negative_tests = db.ListField(db.StringField())
    type = db.StringField()
    experimental = db.BooleanField(default=False)
    two_step = db.BooleanField(default=False)

class Comment(db.EmbeddedDocument):
    owner = db.ReferenceField(User)
    text = db.StringField()
    date = db.DateTimeField(default=datetime.utcnow)
    comment_id = db.ObjectIdField(default=ObjectId)

class Issue(db.Document):
    reaction = db.ReferenceField(Reaction)
    issue_reaction_smiles = db.StringField()
    issue_reaction_svg = db.StringField()
    raised_by = db.ReferenceField(User, reverse_delete_rule=2)
    status = db.StringField(default='Open')
    comments = db.ListField(db.EmbeddedDocumentField(Comment))
    public = db.BooleanField(default=False)
    date = db.DateTimeField(default=datetime.utcnow)



import re

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, SelectField, StringField, PasswordField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, EqualTo, Optional, ValidationError

BUSINESS_CATEGORIES = [
    "Restaurant", "Retail Store", "Professional Service", "Local Business",
    "Health & Wellness", "Beauty & Personal Care", "Home Services", "Other",
]

PASSWORD_MIN_LENGTH = 10
_PASSWORD_SPECIAL_CHARS = r"""!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?"""


def strong_password(form, field):
    # Mirrors user-service's own policy_errors() so the user sees the exact
    # same requirements before the request ever leaves the browser --
    # user-service still re-checks this itself as the actual authority.
    password = field.data or ""
    missing = []
    if len(password) < PASSWORD_MIN_LENGTH:
        missing.append(f"be at least {PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[a-z]", password):
        missing.append("include a lowercase letter")
    if not re.search(r"[A-Z]", password):
        missing.append("include an uppercase letter")
    if not re.search(r"\d", password):
        missing.append("include a digit")
    if not re.search(f"[{re.escape(_PASSWORD_SPECIAL_CHARS)}]", password):
        missing.append("include a special character")
    if missing:
        raise ValidationError("Password must " + ", ".join(missing))


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('Password', validators=[DataRequired(), strong_password])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    account_type = SelectField(
        'Account type',
        choices=[('personal', 'Personal'), ('business', 'Business / Small business')],
        default='personal',
    )
    business_category = SelectField(
        'Business category',
        choices=[('', 'Select a category')] + [(c, c) for c in BUSINESS_CATEGORIES],
        validators=[Optional()],
    )
    business_phone = StringField('Business phone', validators=[Optional(), Length(max=32)])
    business_address = StringField('Business address', validators=[Optional(), Length(max=200)])
    submit = SubmitField('Sign Up')

    def validate_business_category(self, field):
        if self.account_type.data == 'business' and not field.data:
            raise ValidationError('Choose a category for your business')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class PostForm(FlaskForm):
    content = TextAreaField('Content', validators=[DataRequired(), Length(max=2000)])
    photo = FileField('Photo', validators=[Optional(), FileAllowed(['png', 'jpg', 'jpeg', 'gif', 'webp'])])
    submit = SubmitField('Post')

class CommentForm(FlaskForm):
    content = StringField('Comment', validators=[DataRequired(), Length(max=500)])
    submit = SubmitField('Comment')

class RepostForm(FlaskForm):
    comment = StringField('Add a comment (optional)', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Repost')

class MessageForm(FlaskForm):
    content = StringField('Message', validators=[DataRequired(), Length(max=1000)])
    submit = SubmitField('Send')

class EditProfileForm(FlaskForm):
    bio = TextAreaField('Bio', validators=[Optional(), Length(max=300)])
    avatar_url = StringField('Avatar URL', validators=[Optional(), Length(max=500)])
    cover_url = StringField('Cover photo URL', validators=[Optional(), Length(max=500)])
    work = StringField('Work', validators=[Optional(), Length(max=100)])
    education = StringField('Education', validators=[Optional(), Length(max=100)])
    current_city = StringField('Current city', validators=[Optional(), Length(max=100)])
    hometown = StringField('Hometown', validators=[Optional(), Length(max=100)])
    relationship_status = SelectField(
        'Relationship status',
        choices=[
            ('', '—'),
            ('single', 'Single'),
            ('in_a_relationship', 'In a relationship'),
            ('engaged', 'Engaged'),
            ('married', 'Married'),
            ('complicated', "It's complicated"),
        ],
        validators=[Optional()],
    )
    website = StringField('Website', validators=[Optional(), Length(max=200)])
    business_category = SelectField(
        'Business category',
        choices=[('', 'Select a category')] + [(c, c) for c in BUSINESS_CATEGORIES],
        validators=[Optional()],
    )
    business_phone = StringField('Business phone', validators=[Optional(), Length(max=32)])
    business_address = StringField('Business address', validators=[Optional(), Length(max=200)])
    submit = SubmitField('Save')

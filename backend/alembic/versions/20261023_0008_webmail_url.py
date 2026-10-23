"""URL opcional del webmail, independiente de los servidores IMAP y SMTP."""
from alembic import op
import sqlalchemy as sa

revision = '20261023_0008'
down_revision = '20261022_0007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mailboxes', sa.Column('webmail_url', sa.Text()))
    op.create_check_constraint('ck_mailboxes_webmail_url', 'mailboxes',
        "webmail_url IS NULL OR (length(webmail_url) <= 2048 AND webmail_url LIKE 'https://%')")


def downgrade():
    op.drop_constraint('ck_mailboxes_webmail_url', 'mailboxes', type_='check')
    op.drop_column('mailboxes', 'webmail_url')

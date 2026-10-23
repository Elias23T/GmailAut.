from types import SimpleNamespace

import pytest

from app import cli


def test_create_admin_with_username_prompts_secure_password(monkeypatch):
    created_users = []
    unit_of_work = SimpleNamespace(
        users=SimpleNamespace(
            lock_administration=lambda: None,
            by_login=lambda identifier: None,
            add=created_users.append,
        ),
        memberships=SimpleNamespace(),
        tenants=SimpleNamespace(all=lambda: []),
        flush=lambda: None,
        commit=lambda: None,
    )
    session = SimpleNamespace(
        scalar=lambda query: None,
        scalars=lambda query: [],
    )
    monkeypatch.setattr(cli, 'SQLUnitOfWork', lambda session: unit_of_work)
    monkeypatch.setattr(cli, 'ArgonPasswords', lambda: SimpleNamespace(hash=lambda password: 'hashed'))

    cli.create_admin(session, None, 'Administrador', 'adm123', username='admin')

    assert len(created_users) == 1
    assert created_users[0].username == 'admin'
    assert created_users[0].email is None
    assert created_users[0].password_hash == 'hashed'
    assert created_users[0].is_platform_admin is True


@pytest.mark.parametrize(
    ('password', 'username', 'message'),
    [
        ('abc12', 'admin', 'al menos 6'),
        ('adm123', 'a', 'entre 3 y 32'),
    ],
)
def test_create_admin_rejects_weak_password_and_invalid_username(password, username, message):
    session = SimpleNamespace(scalar=lambda query: None)

    with pytest.raises(ValueError, match=message):
        cli.create_admin(session, None, 'Administrador', password, username=username)

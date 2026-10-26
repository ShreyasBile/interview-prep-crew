"""The launcher picks a free port, or reuses a copy of the app that is already running."""

import socket

import pytest

import start


@pytest.fixture
def busy_port():
    """A port held by some other program."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((start.HOST, 0))
    sock.listen()
    yield sock.getsockname()[1]
    sock.close()


def test_free_port_is_used_as_is():
    probe = socket.socket()
    probe.bind((start.HOST, 0))
    port = probe.getsockname()[1]
    probe.close()
    sock, chosen = start.find_port(port, is_ours=lambda p: False)
    assert chosen == port
    sock.close()


def test_busy_port_falls_back_to_the_next_free_one(busy_port):
    sock, chosen = start.find_port(busy_port, is_ours=lambda p: False)
    assert busy_port < chosen < busy_port + start.PORT_ATTEMPTS
    sock.close()


def test_running_copy_of_the_app_is_reused(busy_port):
    sock, chosen = start.find_port(busy_port, is_ours=lambda p: p == busy_port)
    assert sock is None and chosen == busy_port


def test_gives_up_with_a_clear_message_when_no_port_is_free(busy_port):
    with pytest.raises(RuntimeError, match="Set PORT in .env"):
        start.find_port(busy_port, attempts=1, is_ours=lambda p: False)


def test_other_servers_are_not_mistaken_for_the_app(busy_port):
    # a socket that accepts connections but is not Interview Prep Crew
    assert start.is_this_app(busy_port) is False

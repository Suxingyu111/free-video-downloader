from app.services.cookie_store import CookieStore


def test_cookie_store_saves_and_pops_cookie_file(tmp_path):
    store = CookieStore(tmp_path)

    ref = store.save(b"example-cookie")
    path = store.pop(ref)

    assert path is not None
    assert path.read_bytes() == b"example-cookie"
    assert store.pop(ref) is None


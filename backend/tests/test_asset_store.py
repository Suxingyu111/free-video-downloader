from app.services.asset_store import AssetStore


def test_asset_store_registers_remote_asset_without_exposing_url():
    store = AssetStore()

    token = store.register("https://i0.hdslb.com/thumb.jpg", referer="https://www.bilibili.com/video/BV1")
    asset = store.resolve(token)

    assert token
    assert "/" not in token
    assert "hdslb" not in token
    assert asset is not None
    assert asset.url == "https://i0.hdslb.com/thumb.jpg"
    assert asset.referer == "https://www.bilibili.com/video/BV1"


def test_asset_store_rejects_unknown_token():
    store = AssetStore()

    assert store.resolve("missing") is None

"""Item photos: taken on a phone, cleaned on the server, shown in lists and to the holder."""

import io

from PIL import Image

from .test_phase23_assets import me_id, new_asset


def jpeg_with_gps(size=(3000, 2000), color=(200, 30, 30), orientation=None):
    """A camera-like JPEG carrying GPS and camera metadata (and optionally a rotation flag)."""
    img = Image.new("RGB", size, color)
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x0110] = "PhoneModel"  # Model
    if orientation:
        exif[0x0112] = orientation
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (14.0, 33.0, 0.0), "E", (121.0, 1.0, 0.0)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif, quality=90)
    return buf.getvalue()


def add(user, owner_type, owner_id, data, name="IMG_0001.jpg"):
    return user.c.post("/api/v1/photos", headers=user.h, data={"owner_type": owner_type, "owner_id": str(owner_id)}, files={"file": (name, data, "image/jpeg")})


def test_photo_is_cleaned_resized_and_becomes_main(users):
    admin = users["admin"]
    a = new_asset(admin, serial_number="PH-0001").json()
    assert a["photo"] is None
    r = add(admin, "asset", a["id"], jpeg_with_gps(orientation=6))
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["main"] is True
    full = Image.open(io.BytesIO(admin.get(p["full"]).content))
    thumb = Image.open(io.BytesIO(admin.get(p["thumb"]).content))
    # Orientation 6 means "rotate 90°": the stored photo is upright (portrait), long side 1600.
    assert full.size == (1067, 1600) and max(thumb.size) == 480
    # No camera or location data is kept.
    assert len(full.getexif()) == 0 and len(thumb.getexif()) == 0
    # The list row carries the main photo; photos are not in the "Files" list.
    listed = admin.get("/api/v1/assets?q=PH-0001").json()["items"][0]
    assert listed["photo"] == p["thumb"]
    assert admin.get(f"/api/v1/assets/{a['id']}").json()["attachments"] == []


def test_main_photo_switch_remove_and_limits(users):
    admin = users["admin"]
    a = new_asset(admin, serial_number="PH-0002").json()
    first = add(admin, "asset", a["id"], jpeg_with_gps((800, 600))).json()
    second = add(admin, "asset", a["id"], jpeg_with_gps((800, 600), (20, 20, 200))).json()
    assert second["main"] is False
    assert admin.post(f"/api/v1/photos/{second['id']}/main").status_code == 200
    assert admin.get(f"/api/v1/assets/{a['id']}").json()["photo"] == second["thumb"]
    # Removing the main photo promotes the next one.
    assert admin.delete(f"/api/v1/photos/{second['id']}").status_code == 204
    assert admin.get(f"/api/v1/assets/{a['id']}").json()["photo"] == first["thumb"]
    assert admin.get(second["thumb"]).status_code == 404
    for _ in range(7):
        assert add(admin, "asset", a["id"], jpeg_with_gps((400, 300))).status_code == 201
    over = add(admin, "asset", a["id"], jpeg_with_gps((400, 300)))
    assert over.status_code == 422 and "at most 8" in over.json()["detail"]["message"]
    # Not a picture: refused, even with a .jpg name.
    bad = add(admin, "asset", new_asset(admin, serial_number="PH-0009").json()["id"], b"%PDF-1.4 not a photo")
    assert bad.status_code == 422 and "photo" in bad.json()["detail"]["message"]


def test_holder_sees_photo_but_cannot_change_it(users):
    admin, carlo, eli = users["admin"], users["carlo"], users["eli"]
    a = new_asset(admin, serial_number="PH-0003").json()
    p = add(admin, "asset", a["id"], jpeg_with_gps((800, 600))).json()
    admin.post(f"/api/v1/assets/{a['id']}/assign", {"employee_id": me_id(carlo)})
    mine = next(x for x in carlo.get("/api/v1/me/assets").json() if x["id"] == a["id"])
    assert mine["photo"] == p["thumb"]
    assert carlo.get(p["thumb"]).status_code == 200
    assert carlo.get(f"/api/v1/photos?owner_type=asset&owner_id={a['id']}").status_code == 200
    assert add(carlo, "asset", a["id"], jpeg_with_gps((400, 300))).status_code == 403
    assert carlo.delete(f"/api/v1/photos/{p['id']}").status_code == 403
    assert eli.get(p["thumb"]).status_code == 404  # not their asset


def test_vehicle_and_stock_photos(users):
    admin = users["admin"]
    v = admin.post("/api/v1/fleet/vehicles", {"vehicle_type": "Van", "make": "Toyota", "model": "Hiace", "plate_number": "PHO 1001", "status": "active"}).json()
    pv = add(admin, "vehicle", v["id"], jpeg_with_gps((1200, 900))).json()
    assert admin.get(f"/api/v1/fleet/vehicles/{v['id']}").json()["photo"] == pv["thumb"]
    item = admin.post("/api/v1/inventory/items", {"item_code": "PH-INK", "name": "Printer ink", "category": "Consumables", "unit": "pc", "location": "Main store", "on_hand": 4}).json()
    assert "id" in item, item
    pi = add(admin, "inventory_item", item["id"], jpeg_with_gps((1200, 900))).json()
    assert pi["main"] is True
    assert any(i.get("photo") == pi["thumb"] for i in admin.get("/api/v1/inventory/items?q=PH-INK").json()["items"])

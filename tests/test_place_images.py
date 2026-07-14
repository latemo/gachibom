import hashlib
import json
import re
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "web" / "app.js"
SEED_PATH = ROOT / "web" / "data" / "app_recommendation_seed.json"


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    with path.open("rb") as image:
        if image.read(2) != b"\xff\xd8":
            raise AssertionError(f"JPEG signature missing: {path}")
        while True:
            byte = image.read(1)
            if not byte:
                break
            if byte != b"\xff":
                continue
            while byte == b"\xff":
                byte = image.read(1)
            marker = byte[0]
            if marker in {0xD8, 0xD9}:
                continue
            length_bytes = image.read(2)
            if len(length_bytes) != 2:
                break
            segment_length = struct.unpack(">H", length_bytes)[0]
            if marker in sof_markers:
                image.read(1)
                height, width = struct.unpack(">HH", image.read(4))
                return width, height
            image.seek(segment_length - 2, 1)
    raise AssertionError(f"JPEG dimensions not found: {path}")


class PlaceImagePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = APP_PATH.read_text(encoding="utf-8")
        cls.seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        cls.policy_block = cls.app.split("const PLACE_IMAGE_POLICY = {", 1)[1].split(
            "const PLACE_IMAGE_PENDING_REASON = {", 1
        )[0]
        cls.pending_block = cls.app.split("const PLACE_IMAGE_PENDING_REASON = {", 1)[1].split(
            "};", 1
        )[0]

    def test_every_available_place_has_an_image_or_explicit_pending_reason(self):
        active_ids = {
            place["spot_id"]
            for place in self.seed["saved_route_places"]
            if place.get("available") is True
        }
        policy_ids = set(re.findall(r"^\s{2}(jeju_[a-z0-9_]+):", self.policy_block, re.MULTILINE))
        pending_ids = set(re.findall(r"^\s{2}(jeju_[a-z0-9_]+):", self.pending_block, re.MULTILINE))

        self.assertEqual(active_ids, policy_ids | pending_ids)
        self.assertEqual(policy_ids & pending_ids, set())
        self.assertEqual(
            pending_ids,
            {
                "jeju_indoor_bunker_lumieres_010",
                "jeju_restaurant_nangtteule_036",
                "jeju_shopping_donghwa_040",
            },
        )

    def test_policy_assets_exist_decode_and_are_unique(self):
        asset_paths = re.findall(r'"(assets/[^"\n]+\.(?:jpg|JPG))"', self.policy_block)
        policy_ids = re.findall(r"^\s{2}(jeju_[a-z0-9_]+):", self.policy_block, re.MULTILINE)

        self.assertEqual(len(asset_paths), len(policy_ids))
        self.assertEqual(len(asset_paths), len(set(asset_paths)))

        hashes = []
        for relative_path in asset_paths:
            path = ROOT / "web" / relative_path
            self.assertTrue(path.is_file(), relative_path)
            self.assertGreater(path.stat().st_size, 50_000, relative_path)
            width, height = jpeg_dimensions(path)
            self.assertGreaterEqual(width, 800, relative_path)
            self.assertGreaterEqual(height, 500, relative_path)
            hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())

        self.assertEqual(len(hashes), len(set(hashes)))

    def test_unverified_kto_image_rights_are_not_treated_as_reuse_permission(self):
        self.assertNotIn("ktoOriginalPlaceImage", self.app)
        self.assertNotIn("공공누리 제1·3유형 범위", self.app)
        self.assertIn(
            "jeju_shopping_donghwa_040: \"상업 재사용 허용 대표 이미지 확인 중\"",
            self.app,
        )

    def test_seotal_oreum_uses_a_clearly_licensed_neighboring_historic_site_image(self):
        self.assertRegex(
            self.policy_block,
            r"jeju_culture_seotal_oreum_030: commonsPlaceImage\(",
        )
        self.assertIn(
            "https://commons.wikimedia.org/wiki/File:Aldreu_Japanese_underground_hangar_at_WWII.jpg",
            self.policy_block,
        )
        self.assertIn("CC BY-SA 4.0", self.policy_block)

    def test_roadview_policy_links_to_image_dataset(self):
        self.assertIn("https://www.data.go.kr/data/15110209/fileData.do", self.app)
        self.assertIn("이용허락범위 제한 없음 · 16:9 크롭/리사이즈", self.app)


if __name__ == "__main__":
    unittest.main()

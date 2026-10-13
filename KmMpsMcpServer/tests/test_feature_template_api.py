import tempfile
import unittest
from pathlib import Path

from backend import http_api


class FeatureTemplateApiTest(unittest.TestCase):
    def test_parse_feature_template_catalog_keeps_tree_and_leaf_names(self):
        xml = """<?xml version="1.0" encoding="GB2312" ?>
<FeatureSelect>
    <Item name='六面'/>
    <Item name='各类孔特征'>
        <Item name='孔'/>
        <Item name='孔(盲孔)'/>
    </Item>
    <Item name='凹槽特征'>
        <Item name='通槽'/>
    </Item>
</FeatureSelect>
"""

        catalog = http_api._parse_feature_template_xml(xml, "memory.xml")

        self.assertEqual(
            [
                {"name": "六面", "children": []},
                {
                    "name": "各类孔特征",
                    "children": [
                        {"name": "孔", "children": []},
                        {"name": "孔(盲孔)", "children": []},
                    ],
                },
                {
                    "name": "凹槽特征",
                    "children": [
                        {"name": "通槽", "children": []},
                    ],
                },
            ],
            catalog["tree"],
        )
        self.assertEqual(["六面", "各类孔特征", "孔", "孔(盲孔)", "凹槽特征", "通槽"], catalog["flat"])
        self.assertEqual(["六面", "孔", "孔(盲孔)", "通槽"], catalog["leafNames"])
        self.assertEqual("memory.xml", catalog["sourcePath"])

    def test_read_feature_template_catalog_decodes_gb2312_file(self):
        xml = """<?xml version="1.0" encoding="GB2312" ?>
<FeatureSelect>
    <Item name='倒圆倒角特征'>
        <Item name='边倒角'/>
        <Item name='倒圆'/>
    </Item>
</FeatureSelect>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            feature_path = Path(temp_dir) / "FeatureTemplate.xml"
            feature_path.write_bytes(xml.encode("gb2312"))

            catalog = http_api._read_feature_template_catalog(str(feature_path))

        self.assertEqual(["倒圆倒角特征", "边倒角", "倒圆"], catalog["flat"])
        self.assertEqual(["边倒角", "倒圆"], catalog["leafNames"])
        self.assertEqual(str(feature_path), catalog["sourcePath"])

    def test_get_route_exposes_feature_template_endpoint(self):
        source = Path(http_api.__file__).read_text(encoding="utf-8")

        self.assertIn('"/api/feature-template"', source)
        self.assertIn("_handle_get_feature_template", source)


if __name__ == "__main__":
    unittest.main()

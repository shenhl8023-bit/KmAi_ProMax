from __future__ import annotations


def kmsoft_xml_bytes(
    *,
    root_tag: str = "Kmsoft",
    surface_area: float | None = 28736.699,
    inner_rev_area: float | None = 10904.024,
    plane_ratio: float | None = 0.176,
    inner_cyl_ratio: float | None = 0.377,
    outer_cyl_ratio: float | None = 0.416,
    wall_mean: float | None = 3.076,
    max_outer: float | None = 22.0,
    min_inner: float | None = 16.0,
    slenderness: float | None = 2.739,
) -> bytes:
    def param(name: str, value: float | None) -> str:
        if value is None:
            return ""
        return f'<Param name="{name}" type="Double" value="{value}"/>'

    xml = f"""<?xml version="1.0" encoding="GB2312" ?>
<{root_tag}>
  <Item type="Part_Info">
    <Params>
      {param("零件总体表面积", surface_area)}
      {param("零件总体内回转面表面积", inner_rev_area)}
    </Params>
  </Item>
  <Item type="Part_OtherInfo">
    <Item name="面分类信息">
      <Params name="平面信息">{param("平面总面积占比", plane_ratio)}</Params>
      <Params name="外圆柱信息">{param("外圆柱总面积占比", outer_cyl_ratio)}</Params>
      <Params name="内圆柱信息">{param("内圆柱总面积占比", inner_cyl_ratio)}</Params>
    </Item>
    <Item name="薄壁分类信息">
      <Params name="薄壁圆柱信息">{param("薄壁圆柱厚度均值", wall_mean)}</Params>
    </Item>
    <Item name="主回转面信息">
      <Params name="主回转面信息">
        {param("最大外径", max_outer)}
        {param("最小内径", min_inner)}
      </Params>
    </Item>
    <Item name="主惯性轴信息">
      <Params name="主惯性轴信息">{param("零件细长度", slenderness)}</Params>
    </Item>
  </Item>
</{root_tag}>
"""
    return xml.encode("gb2312")

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, Iterable, List
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)


@dataclass
class Cell:
    value: Any = ""
    style: int = 0


@dataclass
class Sheet:
    name: str
    rows: List[List[Cell]] = field(default_factory=list)
    merges: List[str] = field(default_factory=list)
    widths: List[float] = field(default_factory=list)
    freeze_cell: str | None = None


def build_workbook_bytes(sheets: Iterable[Sheet]) -> bytes:
    sheet_list = list(sheets)
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml(len(sheet_list)))
        zf.writestr("_rels/.rels", _root_rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml(sheet_list))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheet_list)))
        zf.writestr("xl/styles.xml", _styles_xml())
        for index, sheet in enumerate(sheet_list, start=1):
            zf.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheet))
    return buffer.getvalue()


def _content_types_xml(sheet_count: int) -> bytes:
    root = ET.Element(f"{{{CONTENT_NS}}}Types")
    ET.SubElement(root, f"{{{CONTENT_NS}}}Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(root, f"{{{CONTENT_NS}}}Default", Extension="xml", ContentType="application/xml")
    ET.SubElement(
        root,
        f"{{{CONTENT_NS}}}Override",
        PartName="/xl/workbook.xml",
        ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    )
    ET.SubElement(
        root,
        f"{{{CONTENT_NS}}}Override",
        PartName="/xl/styles.xml",
        ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml",
    )
    for index in range(1, sheet_count + 1):
        ET.SubElement(
            root,
            f"{{{CONTENT_NS}}}Override",
            PartName=f"/xl/worksheets/sheet{index}.xml",
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _root_rels_xml() -> bytes:
    root = ET.Element(f"{{{PKG_REL_NS}}}Relationships")
    ET.SubElement(
        root,
        f"{{{PKG_REL_NS}}}Relationship",
        Id="rId1",
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
        Target="xl/workbook.xml",
    )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _workbook_xml(sheets: List[Sheet]) -> bytes:
    root = ET.Element(f"{{{MAIN_NS}}}workbook")
    sheets_el = ET.SubElement(root, f"{{{MAIN_NS}}}sheets")
    for index, sheet in enumerate(sheets, start=1):
        ET.SubElement(
            sheets_el,
            f"{{{MAIN_NS}}}sheet",
            name=sheet.name,
            sheetId=str(index),
            attrib={f"{{{REL_NS}}}id": f"rId{index}"},
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _workbook_rels_xml(sheet_count: int) -> bytes:
    root = ET.Element(f"{{{PKG_REL_NS}}}Relationships")
    for index in range(1, sheet_count + 1):
        ET.SubElement(
            root,
            f"{{{PKG_REL_NS}}}Relationship",
            Id=f"rId{index}",
            Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
            Target=f"worksheets/sheet{index}.xml",
        )
    ET.SubElement(
        root,
        f"{{{PKG_REL_NS}}}Relationship",
        Id=f"rId{sheet_count + 1}",
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
        Target="styles.xml",
    )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _styles_xml() -> bytes:
    root = ET.Element(f"{{{MAIN_NS}}}styleSheet")
    num_fmts = ET.SubElement(root, f"{{{MAIN_NS}}}numFmts", count="4")
    ET.SubElement(num_fmts, f"{{{MAIN_NS}}}numFmt", numFmtId="164", formatCode="#,##0")
    ET.SubElement(num_fmts, f"{{{MAIN_NS}}}numFmt", numFmtId="165", formatCode="#,##0.00")
    ET.SubElement(num_fmts, f"{{{MAIN_NS}}}numFmt", numFmtId="166", formatCode="#,##0.0")
    ET.SubElement(num_fmts, f"{{{MAIN_NS}}}numFmt", numFmtId="167", formatCode="#,##0.0%")

    fonts = ET.SubElement(root, f"{{{MAIN_NS}}}fonts", count="3")
    font = ET.SubElement(fonts, f"{{{MAIN_NS}}}font")
    ET.SubElement(font, f"{{{MAIN_NS}}}sz", val="11")
    ET.SubElement(font, f"{{{MAIN_NS}}}name", val="Calibri")
    font = ET.SubElement(fonts, f"{{{MAIN_NS}}}font")
    ET.SubElement(font, f"{{{MAIN_NS}}}b")
    ET.SubElement(font, f"{{{MAIN_NS}}}sz", val="11")
    ET.SubElement(font, f"{{{MAIN_NS}}}name", val="Calibri")
    font = ET.SubElement(fonts, f"{{{MAIN_NS}}}font")
    ET.SubElement(font, f"{{{MAIN_NS}}}b")
    ET.SubElement(font, f"{{{MAIN_NS}}}sz", val="14")
    ET.SubElement(font, f"{{{MAIN_NS}}}name", val="Calibri")

    fills = ET.SubElement(root, f"{{{MAIN_NS}}}fills", count="4")
    ET.SubElement(ET.SubElement(fills, f"{{{MAIN_NS}}}fill"), f"{{{MAIN_NS}}}patternFill", patternType="none")
    ET.SubElement(ET.SubElement(fills, f"{{{MAIN_NS}}}fill"), f"{{{MAIN_NS}}}patternFill", patternType="gray125")
    fill = ET.SubElement(fills, f"{{{MAIN_NS}}}fill")
    pf = ET.SubElement(fill, f"{{{MAIN_NS}}}patternFill", patternType="solid")
    ET.SubElement(pf, f"{{{MAIN_NS}}}fgColor", rgb="FFEDEFF5")
    ET.SubElement(pf, f"{{{MAIN_NS}}}bgColor", indexed="64")
    fill = ET.SubElement(fills, f"{{{MAIN_NS}}}fill")
    pf = ET.SubElement(fill, f"{{{MAIN_NS}}}patternFill", patternType="solid")
    ET.SubElement(pf, f"{{{MAIN_NS}}}fgColor", rgb="FFDDE3F2")
    ET.SubElement(pf, f"{{{MAIN_NS}}}bgColor", indexed="64")

    borders = ET.SubElement(root, f"{{{MAIN_NS}}}borders", count="2")
    ET.SubElement(borders, f"{{{MAIN_NS}}}border")
    border = ET.SubElement(borders, f"{{{MAIN_NS}}}border")
    for edge in ("left", "right", "top", "bottom"):
        ET.SubElement(border, f"{{{MAIN_NS}}}{edge}", style="thin")

    ET.SubElement(root, f"{{{MAIN_NS}}}cellStyleXfs", count="1")
    ET.SubElement(root.find(f"{{{MAIN_NS}}}cellStyleXfs"), f"{{{MAIN_NS}}}xf", numFmtId="0", fontId="0", fillId="0", borderId="0")

    cell_xfs = ET.SubElement(root, f"{{{MAIN_NS}}}cellXfs", count="9")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="0", fontId="0", fillId="0", borderId="0", xfId="0")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="0", fontId="2", fillId="0", borderId="0", xfId="0", applyFont="1")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="0", fontId="1", fillId="2", borderId="1", xfId="0", applyFont="1", applyFill="1", applyBorder="1")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="0", fontId="1", fillId="3", borderId="1", xfId="0", applyFont="1", applyFill="1", applyBorder="1")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="164", fontId="0", fillId="0", borderId="1", xfId="0", applyNumberFormat="1", applyBorder="1")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="165", fontId="0", fillId="0", borderId="1", xfId="0", applyNumberFormat="1", applyBorder="1")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="166", fontId="0", fillId="0", borderId="1", xfId="0", applyNumberFormat="1", applyBorder="1")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="0", fontId="0", fillId="0", borderId="1", xfId="0", applyBorder="1")
    ET.SubElement(cell_xfs, f"{{{MAIN_NS}}}xf", numFmtId="0", fontId="1", fillId="0", borderId="0", xfId="0", applyFont="1")

    ET.SubElement(root, f"{{{MAIN_NS}}}cellStyles", count="1")
    ET.SubElement(root.find(f"{{{MAIN_NS}}}cellStyles"), f"{{{MAIN_NS}}}cellStyle", name="Normal", xfId="0", builtinId="0")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _sheet_xml(sheet: Sheet) -> bytes:
    root = ET.Element(f"{{{MAIN_NS}}}worksheet")
    max_col = max((len(row) for row in sheet.rows), default=1)
    ET.SubElement(root, f"{{{MAIN_NS}}}dimension", ref=f"A1:{_column_letter(max_col)}{max(len(sheet.rows), 1)}")
    if sheet.widths:
        cols = ET.SubElement(root, f"{{{MAIN_NS}}}cols")
        for index, width in enumerate(sheet.widths, start=1):
            ET.SubElement(cols, f"{{{MAIN_NS}}}col", min=str(index), max=str(index), width=str(width), customWidth="1")
    if sheet.freeze_cell:
        sheet_views = ET.SubElement(root, f"{{{MAIN_NS}}}sheetViews")
        sheet_view = ET.SubElement(sheet_views, f"{{{MAIN_NS}}}sheetView", workbookViewId="0")
        pane = ET.SubElement(sheet_view, f"{{{MAIN_NS}}}pane", topLeftCell=sheet.freeze_cell, state="frozen")
        if sheet.freeze_cell[0].isalpha() and sheet.freeze_cell[1:].isdigit():
            col = _column_index_from_ref(sheet.freeze_cell)
            row = int("".join(ch for ch in sheet.freeze_cell if ch.isdigit()))
            if col > 1:
                pane.set("xSplit", str(col - 1))
            if row > 1:
                pane.set("ySplit", str(row - 1))
            pane.set("activePane", "bottomRight" if col > 1 and row > 1 else "bottomLeft" if row > 1 else "topRight")
    sheet_data = ET.SubElement(root, f"{{{MAIN_NS}}}sheetData")
    for row_index, row in enumerate(sheet.rows, start=1):
        row_el = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", r=str(row_index))
        row_has_value = False
        for col_index, cell in enumerate(row, start=1):
            if cell.value in ("", None):
                continue
            row_has_value = True
            cell_el = ET.SubElement(
                row_el,
                f"{{{MAIN_NS}}}c",
                r=f"{_column_letter(col_index)}{row_index}",
                s=str(cell.style),
            )
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                ET.SubElement(cell_el, f"{{{MAIN_NS}}}v").text = str(cell.value)
            else:
                cell_el.set("t", "inlineStr")
                is_el = ET.SubElement(cell_el, f"{{{MAIN_NS}}}is")
                ET.SubElement(is_el, f"{{{MAIN_NS}}}t").text = str(cell.value)
        if not row_has_value:
            row_el.attrib.pop("r", None)
            sheet_data.remove(row_el)
    if sheet.merges:
        merges = ET.SubElement(root, f"{{{MAIN_NS}}}mergeCells", count=str(len(sheet.merges)))
        for merge_ref in sheet.merges:
            ET.SubElement(merges, f"{{{MAIN_NS}}}mergeCell", ref=merge_ref)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _column_letter(index: int) -> str:
    letters = []
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def _column_index_from_ref(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for char in letters:
        value = value * 26 + ord(char.upper()) - 64
    return value

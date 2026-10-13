# -*- coding: utf-8 -*-
"""NX 11 journal: batch convert Parasolid .x_t files to real STEP AP214 files.

Run this file from NX (File -> Execute -> NX Open), not with a normal Python
interpreter. Only SOURCE_FOLDER normally needs to be changed.

The conversion intentionally uses a unique temporary .prt for every source
part. Part.SaveAs is only used to create that native NX temporary file; the
final .stp is always produced by NX's Step214Creator translator.
"""

from __future__ import print_function

import datetime
import hashlib
import ntpath
import os
import shutil
import sys

import NXOpen


# ======================== Change this path only ========================
SOURCE_FOLDER = r"C:\Users\Administrator\Desktop\part_data"
# ======================================================================

# Leave empty to let the script locate step214ug.def from the NX install.
STEP214_SETTINGS_FILE = r""


def source_names(names):
    """Return .x_t names in a deterministic, case-insensitive order."""
    result = [name for name in names if str(name).lower().endswith(".x_t")]
    return sorted(result, key=lambda value: str(value).lower())


def output_name(source_path):
    """Map C:\\folder\\part.x_t to part.stp on every operating system."""
    filename = ntpath.basename(source_path)
    return os.path.splitext(filename)[0] + ".stp"


def short_hash(path):
    digest = hashlib.sha256()
    handle = open(path, "rb")
    try:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    finally:
        handle.close()
    return digest.hexdigest()[:16]


def find_step214_settings():
    if STEP214_SETTINGS_FILE:
        candidate = os.path.abspath(STEP214_SETTINGS_FILE)
        if os.path.isfile(candidate):
            return candidate
        raise RuntimeError("STEP214_SETTINGS_FILE does not exist: " + candidate)

    base_dir = os.environ.get("UGII_BASE_DIR", "")
    root_dir = os.environ.get("UGII_ROOT_DIR", "")
    candidates = [
        os.path.join(base_dir, "step214ug", "step214ug.def"),
        os.path.join(base_dir, "STEP214UG", "step214ug.def"),
        os.path.join(root_dir, "step214ug.def"),
        os.path.join(root_dir, "step214ug", "step214ug.def"),
        os.path.join(root_dir, "..", "step214ug", "step214ug.def"),
    ]
    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if os.path.isfile(candidate):
            return candidate

    raise RuntimeError(
        "Cannot find step214ug.def. Set STEP214_SETTINGS_FILE at the top "
        "of this script to the full path of your NX 11 step214ug.def file."
    )


def close_all_without_saving(session):
    """Support the two CloseAll signatures found in NX 11 installations."""
    try:
        session.Parts.CloseAll()
        return
    except Exception:
        pass

    try:
        session.Parts.CloseAll(NXOpen.Part.CloseStatus.DoNotSaveChanges)
    except Exception as exc:
        print("WARN: CloseAll failed: %s" % exc)


def open_source_as_display_part(session, source_path):
    """Open one Parasolid file as the active display/work part."""
    if hasattr(session.Parts, "OpenBaseDisplay"):
        result = session.Parts.OpenBaseDisplay(source_path)
    else:
        result = session.Parts.Open(source_path)

    load_status = None
    if isinstance(result, tuple):
        part = result[0]
        if len(result) > 1:
            load_status = result[1]
    else:
        part = result

    if load_status is not None and hasattr(load_status, "Dispose"):
        load_status.Dispose()
    if part is None:
        part = session.Parts.Work
    if part is None:
        raise RuntimeError("NX returned no part after opening: " + source_path)

    work_part = session.Parts.Work
    if work_part is None or work_part.Tag != part.Tag:
        if hasattr(session.Parts, "SetWork"):
            session.Parts.SetWork(part)
        work_part = session.Parts.Work

    if work_part is None or work_part.Tag != part.Tag:
        raise RuntimeError(
            "Opened part did not become the NX Work Part. Source: " + source_path
        )
    return part


def part_dimensions(part):
    """Best-effort overall body bounding size for the conversion log."""
    try:
        import NXOpen.UF

        uf_session = NXOpen.UF.UFSession.GetUFSession()
        bounds = None
        for body in part.Bodies:
            box = uf_session.Modl.AskBoundingBox(body.Tag)
            if box is None or len(box) < 6:
                continue
            if bounds is None:
                bounds = list(box[:6])
            else:
                bounds[0] = min(bounds[0], box[0])
                bounds[1] = min(bounds[1], box[1])
                bounds[2] = min(bounds[2], box[2])
                bounds[3] = max(bounds[3], box[3])
                bounds[4] = max(bounds[4], box[4])
                bounds[5] = max(bounds[5], box[5])
        if bounds is None:
            return "unavailable"
        return "%.6f x %.6f x %.6f" % (
            bounds[3] - bounds[0],
            bounds[4] - bounds[1],
            bounds[5] - bounds[2],
        )
    except Exception as exc:
        return "unavailable (%s)" % exc


def export_step214(session, input_prt, output_stp, settings_file):
    """Export a native NX part to a genuine STEP AP214 file."""
    creator = session.DexManager.CreateStep214Creator()
    try:
        creator.ExportAs = NXOpen.Step214Creator.ExportAsOption.Ap214
        creator.SettingsFile = settings_file
        creator.ObjectTypes.Solids = True
        creator.InputFile = input_prt
        creator.OutputFile = output_stp
        creator.FileSaveFlag = False

        if hasattr(creator, "LayerMask"):
            creator.LayerMask = "1-256"
        if hasattr(creator, "ProcessHoldFlag"):
            creator.ProcessHoldFlag = True

        creator.Commit()
    finally:
        creator.Destroy()

    if not os.path.isfile(output_stp):
        raise RuntimeError("STEP exporter did not create: " + output_stp)
    if os.path.getsize(output_stp) <= 0:
        raise RuntimeError("STEP exporter created an empty file: " + output_stp)


def make_output_directories(source_folder):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = os.path.join(source_folder, "STEP_EXPORT_" + stamp)
    temp_folder = os.path.join(output_folder, "_temp_prt")
    os.makedirs(temp_folder)
    return output_folder, temp_folder


def list_source_paths(source_folder):
    names = source_names(os.listdir(source_folder))
    return [os.path.join(source_folder, name) for name in names]


def convert_one(session, source_path, output_folder, temp_folder, settings_file):
    base = os.path.splitext(os.path.basename(source_path))[0]
    temp_prt = os.path.join(temp_folder, base + ".prt")
    output_stp = os.path.join(output_folder, output_name(source_path))

    # Starting every conversion with an empty NX session prevents a previous
    # Work Part from being exported again under the next file name.
    close_all_without_saving(session)
    part = open_source_as_display_part(session, source_path)

    work_part = session.Parts.Work
    work_path = getattr(work_part, "FullPath", "") or getattr(work_part, "Name", "")
    print("SOURCE    : %s" % source_path)
    print("SOURCE SHA: %s" % short_hash(source_path))
    print("WORK PART : %s" % work_path)
    print("SIZE XYZ  : %s" % part_dimensions(part))

    # SaveAs is valid here because the destination is a native temporary .prt.
    # It must never be used directly with output_stp.
    part.SaveAs(temp_prt)
    if not os.path.isfile(temp_prt):
        raise RuntimeError("NX did not create temporary part: " + temp_prt)

    export_step214(session, temp_prt, output_stp, settings_file)
    print("OUTPUT    : %s" % output_stp)
    print("OUTPUT SHA: %s" % short_hash(output_stp))

    close_all_without_saving(session)
    os.remove(temp_prt)
    return output_stp


def main():
    source_folder = os.path.abspath(SOURCE_FOLDER)
    if not os.path.isdir(source_folder):
        raise RuntimeError("SOURCE_FOLDER does not exist: " + source_folder)

    files = list_source_paths(source_folder)
    if not files:
        raise RuntimeError("No .x_t files found in: " + source_folder)

    settings_file = find_step214_settings()
    output_folder, temp_folder = make_output_directories(source_folder)
    session = NXOpen.Session.GetSession()

    print("NX batch Parasolid -> STEP AP214")
    print("INPUT     : %s" % source_folder)
    print("OUTPUT DIR: %s" % output_folder)
    print("SETTINGS  : %s" % settings_file)
    print("COUNT     : %d" % len(files))

    ok_count = 0
    failed = []
    for index, source_path in enumerate(files, 1):
        print("")
        print("[%d/%d] --------------------------------------------------" % (index, len(files)))
        try:
            convert_one(
                session,
                source_path,
                output_folder,
                temp_folder,
                settings_file,
            )
            ok_count += 1
            print("RESULT    : OK")
        except Exception as exc:
            failed.append((source_path, repr(exc)))
            print("RESULT    : FAILED - %s" % repr(exc))
            close_all_without_saving(session)

    if os.path.isdir(temp_folder) and not os.listdir(temp_folder):
        os.rmdir(temp_folder)

    print("")
    print("========================= SUMMARY =========================")
    print("OK=%d FAILED=%d TOTAL=%d" % (ok_count, len(failed), len(files)))
    print("OUTPUT DIR: %s" % output_folder)
    for source_path, error in failed:
        print("FAILED: %s -> %s" % (source_path, error))

    if failed:
        raise RuntimeError("%d conversion(s) failed; see the NX listing window." % len(failed))


if __name__ == "__main__":
    main()


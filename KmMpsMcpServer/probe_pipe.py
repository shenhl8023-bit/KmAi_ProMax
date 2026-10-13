#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
3DMPS 命名管道函数探测脚本

通过向 \\\\.\\pipe\\3dmps_service 发送不同 function name，
探测 3DMPS 主程序实际支持哪些 API。

使用方法：
1. 启动 3DMPS 主程序（Km3dmps.exe）
2. python probe_pipe.py
3. 查看生成的 probe_results.json 和控制台输出
"""

from __future__ import print_function

import ctypes
import json
import os
import sys
import time
import traceback

PIPE_NAME = u"\\\\.\\pipe\\3dmps_service"
BUFFER_SIZE = 64 * 1024
MAX_RESPONSE_SIZE = 8 * 1024 * 1024
RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_results.json")


class NamedPipeClient(object):
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    ERROR_MORE_DATA = 234

    def __init__(self, pipe_name):
        self.pipe_name = pipe_name
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def call(self, function_name, params=None, timeout_ms=5000):
        """调用命名管道函数。"""
        if params is None:
            params = {}
        request = {"function": function_name, "params": params}
        payload = json.dumps(request, ensure_ascii=False).encode("utf-8")

        handle = self.kernel32.CreateFileW(
            self.pipe_name,
            self.GENERIC_READ | self.GENERIC_WRITE,
            0, None, self.OPEN_EXISTING, 0, None,
        )
        if handle == self.INVALID_HANDLE_VALUE:
            error_code = ctypes.get_last_error()
            raise WindowsError(error_code, u"无法连接 3DMPS 命名管道")

        try:
            written = ctypes.c_ulong(0)
            ok = self.kernel32.WriteFile(
                handle, ctypes.c_char_p(payload),
                len(payload), ctypes.byref(written), None,
            )
            if not ok:
                error_code = ctypes.get_last_error()
                raise WindowsError(error_code, u"写入失败")

            chunks = []
            total = 0
            while True:
                buffer = ctypes.create_string_buffer(BUFFER_SIZE)
                read = ctypes.c_ulong(0)
                ok = self.kernel32.ReadFile(
                    handle, buffer, BUFFER_SIZE, ctypes.byref(read), None,
                )
                chunk = buffer.raw[:read.value]
                if chunk:
                    chunks.append(chunk)
                    total += len(chunk)
                if total > MAX_RESPONSE_SIZE:
                    return {"_error": "response_too_large", "_size": total}
                if ok:
                    break
                error_code = ctypes.get_last_error()
                if error_code != self.ERROR_MORE_DATA:
                    raise WindowsError(error_code, u"读取失败")

            response_bytes = b"".join(chunks)
            response_text = response_bytes.decode("utf-8", "replace")
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                return {"_raw": response_text[:500]}
        finally:
            self.kernel32.CloseHandle(handle)


# ============================================
# 候选函数列表
# ============================================

# 已知的 4 个函数（基准对照）
KNOWN_FUNCTIONS = [
    {"name": "get_all_bof_item", "params": {}},
    {"name": "do_ai_process_route", "params": {"arg1": 1}},
    {"name": "open_prt_file", "params": {"arg1": "D:\\test.prt"}},
    {"name": "process_prt_file", "params": {"arg1": "D:\\test.prt", "arg2": ""}},
]

# 基于 CommandMessage.h 枚举转换的候选名
COMMAND_MSG_CANDIDATES = [
    "id_kmmps_file_new", "id_kmmps_file_open", "id_kmmps_file_save",
    "id_kmmps_pick_auto", "id_kmmps_pick_hand",
    "id_kmmps_design_rough_import", "id_kmmps_design_rough_create",
    "id_kmmps_design_rough_surplus", "id_kmmps_design_rough_cast",
    "id_kmmps_design_rough_combine", "id_kmmps_design_set_processface",
    "id_kmmps_design_reason_auto", "id_kmmps_design_reason_auto_semi",
    "id_kmmps_design_process_num_reset", "id_kmmps_design_process_rapid_create",
    "id_kmmps_desigb_step_arrange",
    "id_kmmps_design_processmodel_create_all",
    "id_kmmps_design_processmodel_create_interval",
    "id_kmmps_design_processmodel_create_current",
    "id_kmmps_design_set_processcolor",
    "id_kmmps_design_pmianalysis", "id_kmmps_design_programmme_origin",
    "id_kmmps_design_projectsymbol", "id_kmmps_design_reload_pmi",
    "id_kmmps_design_autosignpmi",
    "id_kmmps_interactive_highlight", "id_kmmps_pick_report", "id_kmmps_high_light",
    "id_kmmps_option_pmi_on", "id_kmmps_option_bof_on", "id_kmmps_option_bop_on",
    "id_kmmps_option_steptemplate_on",
    "id_kmmps_option_tentag_on", "id_kmmps_option_hideemptystep",
    "id_kmmps_option_surface_overuse_on", "id_kmmps_option_surface_overuse_off",
    "id_kmmps_option_surface_common_autospread_on",
    "id_kmmps_option_surface_common_autospread_off",
    "id_kmmps_option_isupdate", "id_kmmps_option_restrain_assign",
    "id_kmmps_option_rough_line", "id_kmmps_option_rough_body",
    "id_kmmps_option_rough_hide",
    "id_kmmps_tool_pdf", "id_kmmps_tool_excel", "id_kmmps_tool_gxk",
    "id_kmmps_proccheck_dimchaincalculator", "id_kmmps_proccheck_dimchaincheck",
    "id_mpstool_checkrule", "id_mpstool_checksurf", "id_mpstool_selector",
    "id_mpstool_testfunc", "id_reuse_open", "id_reuse_feature_connect",
    "id_kmmps_check_processstep", "id_kmmps_check_process_compare",
    "id_kmmps_check_model_compare",
    "id_kmmps_option_pmi_off", "id_kmmps_option_bof_off", "id_kmmps_option_bop_off",
    "ids_kmmps_setting", "ids_kmmps_about",
    "id_kmmps_start_record_command", "id_kmmps_auto_execute_command",
    "id_kmmps_save_command",
]

# 基于 CommandResponse.cpp 中的 C++ 方法名转换
CPP_METHOD_CANDIDATES = [
    "DoNewFile", "do_new_file", "DoOpen", "do_open", "DoSave", "do_save",
    "DoSaveDocument", "do_save_document",
    "FeatureIdentify", "feature_identify", "FeatureInference", "feature_inference",
    "ManualFeatIdentify", "manual_feat_identify",
    "ImportRough", "import_rough", "CreateRough", "create_rough",
    "AutoGenRough", "auto_gen_rough",
    "DesignRoughSurplus", "design_rough_surplus",
    "CreateProcessModel", "create_process_model",
    "CreateStepNode", "create_step_node", "CreateGroupNode", "create_group_node",
    "GetModelViewPosition", "get_model_view_position",
    "GetProgramOrgInfo", "get_program_org_info",
    "CreateProgrammeOrigin", "create_programme_origin",
    "CheckProcessStep", "check_process_step",
    "GetCurModelFeatAttributeVector", "get_cur_model_feat_attribute_vector",
    "GetCurModelNum", "get_cur_model_num",
    "GetHighLighSelItems", "get_high_ligh_sel_items",
    "SetHighLightVisible", "set_high_light_visible",
    "ShowIdentifyReport", "show_identify_report",
    "SavePartAs", "save_part_as",
    "RemoveFeatures", "remove_features",
    "SetProcFeatureVisible", "set_proc_feature_visible",
    "FeatHighlight", "feat_highlight",
    "AddProcModel", "add_proc_model",
    "UpdateProcessModel", "update_process_model",
    "UpdateProcessNodeGrid", "update_process_node_grid",
    "UpdateStepNodeGrid", "update_step_node_grid",
    "ResetStepNumber", "reset_step_number",
    "CloseModel", "close_model",
    "Open3DModel", "open_3d_model",
    "Close3DModel", "close_3d_model",
    "GetDirectoryManager", "get_directory_manager",
    "SetCurrentPartPath", "set_current_part_path",
    "SetCurrentModel", "set_current_model",
    "AddDeleteFeatureSurface", "add_delete_feature_surface",
    "FeatMatrixDistribute", "feat_matrix_distribute",
    "FeatCircleDistrubute", "feat_circle_distribute",
    "FeatLineDistribute", "feat_line_distribute",
    "FeatMirrorDistribute", "feat_mirror_distribute",
    "FeatRepeatDistribute", "feat_repeat_distribute",
    "FeatCircleDirDistribute", "feat_circle_dir_distribute",
    "FeatAssignPlaneDistribute", "feat_assign_plane_distribute",
    "FeatSameDirSameHighDistribute", "feat_same_dir_same_high_distribute",
    "EditCutBody", "edit_cut_body",
    "EnterPureSlotOutlineDesign", "enter_pure_slot_outline_design",
    "SlotExtern", "slot_extern",
]

# 基于源文件名/类名推测的导出名
MODULE_CANDIDATES = [
    "GenProcess", "gen_process", "ArrangeStep", "arrange_step",
    "GroupArrange", "group_arrange", "CastRoughDesign", "cast_rough_design",
    "ProcessModelValidation", "process_model_validation",
    "ModelCompare", "model_compare",
    "MultipleBoolean", "multiple_boolean",
    "BofCut", "bof_cut", "BofPaste", "bof_paste",
    "BopAdd", "bop_add", "BopDelete", "bop_delete", "BopInsert", "bop_insert",
    "BotDelete", "bot_delete",
    "AddStep", "add_step", "DeleteStep", "delete_step", "InsertStep", "insert_step",
]

# 工艺推理相关
AI_CANDIDATES = [
    "ai_process_route", "ai_run_inference", "ai_inference",
    "run_ai_process_route", "generate_process",
    "auto_generate_route", "auto_route", "auto_process",
    "infer_process", "reason_auto", "reason_userdefine",
    "feature_inference", "process_inference",
    "feature_recognition", "auto_recognition",
]

# BOF/BOP 数据查询
QUERY_CANDIDATES = [
    "get_bof_tree", "get_bop_tree", "get_bot_tree",
    "get_features", "get_process_steps", "get_process_route",
    "get_cur_model_info", "get_model_info", "get_part_info",
    "get_current_part", "get_open_model",
    "get_process_list", "get_step_list", "get_group_list",
    "get_rough_info", "get_allowance_info",
    "list_features", "list_processes",
    "bof_get_all", "bop_get_all", "bot_get_all",
]

# 文件操作
FILE_CANDIDATES = [
    "save_file", "save_as", "save_document",
    "new_file", "new_project", "close_file", "close_model",
    "import_rough_file", "import_file",
    "export_pdf", "export_excel", "export_gxk", "export_mpd",
    "load_file", "read_file",
    "auto_save", "save_command",
]

# 工艺操作
PROCESS_CANDIDATES = [
    "arrange_step", "rapid_create", "create_step", "add_step",
    "reset_step_number", "set_process_color",
    "auto_identify", "manual_identify", "auto_pick",
    "create_group", "add_group", "delete_group",
    "create_route_template", "apply_route_template",
    "generate_pdf", "generate_excel", "generate_gxk",
    "check_process", "check_model", "check_step",
    "highlight", "show_highlight", "hide_highlight",
    "reload_pmi", "auto_sign_pmi", "pmi_analysis",
]

ALL_CANDIDATES = []
seen = set()
for c in KNOWN_FUNCTIONS + [{"name": n, "params": {}} for n in COMMAND_MSG_CANDIDATES] \
        + [{"name": n, "params": {}} for n in CPP_METHOD_CANDIDATES] \
        + [{"name": n, "params": {}} for n in MODULE_CANDIDATES] \
        + [{"name": n, "params": {}} for n in AI_CANDIDATES] \
        + [{"name": n, "params": {}} for n in QUERY_CANDIDATES] \
        + [{"name": n, "params": {}} for n in FILE_CANDIDATES] \
        + [{"name": n, "params": {}} for n in PROCESS_CANDIDATES]:
    if c["name"] not in seen:
        seen.add(c["name"])
        ALL_CANDIDATES.append(c)


def classify_response(name, response, elapsed_ms):
    """
    根据响应内容判断函数是否真实存在。
    返回: ("valid" | "unknown" | "param_error" | "model_required" | "other", 简短描述)
    """
    if response is None:
        return "other", "no response"

    if isinstance(response, dict):
        status = response.get("status", "")
        msg = str(response.get("message", ""))

        if status == "success":
            return "valid", "success"
        if "unknown" in msg.lower() or "not found" in msg.lower() or "invalid" in msg.lower():
            return "unknown", msg[:80]
        if "param" in msg.lower() or "missing" in msg.lower() or "arg" in msg.lower():
            return "param_error", msg[:80]
        if "model" in msg.lower() or "part" in msg.lower() or "open" in msg.lower() or "file" in msg.lower():
            return "model_required", msg[:80]
        return "other", (status + ": " + msg)[:80]

    return "other", str(response)[:80]


def main():
    print("=" * 70)
    print("3DMPS 命名管道函数探测工具")
    print("=" * 70)
    print("管道: %s" % PIPE_NAME)
    print("候选数: %d" % len(ALL_CANDIDATES))
    print()

    pipe = NamedPipeClient(PIPE_NAME)

    # 先检测连接
    try:
        pipe.call("ping", {})
    except WindowsError as exc:
        print("[!] 无法连接命名管道: %s" % exc)
        print("[!] 请确认 3DMPS 主程序已经启动。")
        sys.exit(1)

    # 已知函数（基线测试）
    print("\n[基线] 测试已知的 4 个函数...")
    for c in KNOWN_FUNCTIONS:
        try:
            resp = pipe.call(c["name"], c["params"])
            print("  [OK] %s" % c["name"])
        except Exception as exc:
            print("  [FAIL] %s -> %s" % (c["name"], exc))

    # 探测候选
    results = []
    print("\n[探测] 开始扫描 %d 个候选函数名..." % len(ALL_CANDIDATES))
    print("(这一步会比较慢，每条测试有超时保护)\n")

    valid = []
    unknown = []
    other = []

    for i, c in enumerate(ALL_CANDIDATES):
        name = c["name"]
        params = c.get("params", {})
        t0 = time.time()
        try:
            resp = pipe.call(name, params)
            elapsed = (time.time() - t0) * 1000
            kind, desc = classify_response(name, resp, elapsed)
            results.append({
                "name": name,
                "kind": kind,
                "desc": desc,
                "elapsed_ms": round(elapsed, 1),
                "params": params,
                "response_sample": str(resp)[:300],
            })
            if kind == "valid":
                valid.append(name)
                print("  [VALID]    %s" % name)
            elif kind == "unknown":
                unknown.append(name)
                if i < 50 or i % 20 == 0:
                    print("  [unknown]  %s" % name)
            else:
                other.append(name)
                print("  [%s]  %s -> %s" % (kind.upper(), name, desc))
        except Exception as exc:
            elapsed = (time.time() - t0) * 1000
            err = str(exc)
            kind = "unknown" if "unknown" in err.lower() or "无效" in err else "exception"
            results.append({
                "name": name,
                "kind": kind,
                "desc": err[:80],
                "elapsed_ms": round(elapsed, 1),
                "params": params,
                "response_sample": None,
            })
            if kind == "unknown":
                unknown.append(name)
            else:
                other.append(name)
                print("  [EXCEPTION] %s -> %s" % (name, err[:80]))

    # 输出汇总
    print("\n" + "=" * 70)
    print("探测结果汇总")
    print("=" * 70)
    print("总数: %d" % len(results))
    print("可能可用 (valid):     %d" % len(valid))
    print("明确未知 (unknown):   %d" % len(unknown))
    print("其它情况 (other):     %d" % len(other))
    print()

    if valid:
        print("\n[可能可用] 这些函数返回 success：")
        for n in valid:
            print("  - %s" % n)

    if other:
        print("\n[其它情况] 这些函数返回错误但不是 unknown，可能需要特定参数/状态：")
        for n in other:
            r = next(x for x in results if x["name"] == n)
            print("  - %-50s [%s] %s" % (n, r["kind"], r["desc"]))

    # 保存详细结果
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n详细结果已写入: %s" % RESULTS_FILE)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] 用户中断")
        sys.exit(0)
    except Exception as exc:
        print("\n[!] 异常: %s" % exc)
        traceback.print_exc()
        sys.exit(1)
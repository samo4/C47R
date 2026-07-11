"""
KiCad PCB/SCH Fixer v2
=======================
Fixes linking between schematic symbols and PCB footprints by:
1. Adding proper library prefix to PCB footprint names (FPID matching)
2. Adding (path ...) properties for UUID-based matching
3. Updating fp-lib-table with needed libraries

Usage: python fix_pcb_paths.py
"""

import re
import sys

SCH_FILE = r"c47r.kicad_sch"
PCB_FILE = r"c47r.kicad_pcb"
FP_LIB_TABLE = r"fp-lib-table"

# Map PCB footprint types to their full library-qualified names
FOOTPRINT_LIB_MAP = {
    "SW_Cherry_MX_PCB_1.00u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_1.25u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_1.25u_90deg": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_1.50u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_1.50u_90deg": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_1.75u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_1.75u_90deg": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_2.00u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_2.00u_90deg": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_2.25u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_2.25u_90deg": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_2.50u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_2.50u_90deg": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_2.75u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_2.75u_90deg": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_3.00u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_3.00u_90deg": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_4.00u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_4.50u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_5.50u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_6.00u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_6.00u_Offset": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_6.25u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_6.50u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_7.00u": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB_ISOEnter": "Switch_Keyboard_Cherry_MX",
    "SW_Cherry_MX_PCB": "Switch_Keyboard_Cherry_MX",
    "D_SOD-123": "Diode_SMD",
    "Stabilizer_Cherry_MX_2.00u": "Mounting_Keyboard_Stabilizer",
}

# Map footprint type to schematic footprint reference (for the reference map)
FOOTPRINT_SCH_REF_MAP = {
    "SW_Cherry_MX_PCB_1.00u": "Switch_Keyboard_Cherry_MX:SW_Cherry_MX_PCB_1.00u",
    "SW_Cherry_MX_PCB_2.00u": "Switch_Keyboard_Cherry_MX:SW_Cherry_MX_PCB_2.00u",
    "D_SOD-123": "Diode_SMD:D_SOD-123",
    "D_SOD-323": "Diode_SMD:D_SOD-323",
    "Stabilizer_Cherry_MX_2.00u": "Mounting_Keyboard_Stabilizer:Stabilizer_Cherry_MX_2.00u",
}

MISSING_LIBRARIES = [
    '(lib (name "Diode_SMD")(type "KiCad")(uri "${KICAD8_FOOTPRINT_DIR}/Diode_SMD.pretty")(options "")(descr ""))',
    '(lib (name "Mounting_Keyboard_Stabilizer")(type "KiCad")(uri "${KICAD8_FOOTPRINT_DIR}/Mounting_Keyboard_Stabilizer.pretty")(options "")(descr ""))',
]


def parse_schematic(sch_path):
    """Parse schematic to extract root UUID and ref->symbol UUID mapping."""
    with open(sch_path, 'r', encoding='utf-8') as f:
        content = f.read()

    m = re.search(r'\(uuid "([^"]+)"\)', content)
    if not m:
        print("ERROR: Could not find schematic root UUID")
        sys.exit(1)
    root_uuid = m.group(1)
    print(f"Schematic root UUID: {root_uuid}")

    first_ef = content.find('(embedded_fonts no)')
    second_ef = content.find('(embedded_fonts no)', first_ef + 1)
    if second_ef == -1:
        print("ERROR: Could not find root (embedded_fonts no)")
        sys.exit(1)

    instances_section = content[second_ef + len('(embedded_fonts no)'):]
    ref_to_uuid = {}
    symbol_pattern = re.compile(r'\(symbol\s+\(lib_id\s+"[^"]*"\)')

    for match in symbol_pattern.finditer(instances_section):
        start = match.start()
        depth = 0
        i = start
        while i < len(instances_section):
            ch = instances_section[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1

        block = instances_section[start:i + 1]
        uuid_m = re.search(r'uuid "([^"]+)"', block)
        ref_m = re.search(r'\(property "Reference"\s+"([^"]+)"', block)
        if uuid_m and ref_m:
            ref_to_uuid[ref_m.group(1)] = uuid_m.group(1)

    print(f"Total symbols found: {len(ref_to_uuid)}")
    return root_uuid, ref_to_uuid


def fix_pcb(pcb_path, root_uuid, ref_to_uuid):
    """
    Fix PCB:
    1. Add library prefix to footprint names (FPID matching)
    2. Add (path ...) properties
    """
    with open(pcb_path, 'r', encoding='utf-8') as f:
        content = f.read()

    result = []
    i = 0
    path_changes = 0
    fpid_changes = 0
    fp_pattern = re.compile(r'\(footprint "([^"]*)"')

    while i < len(content):
        fp_match = fp_pattern.search(content, i)
        if not fp_match:
            result.append(content[i:])
            break

        start = fp_match.start()
        result.append(content[i:start])

        # Find the end of this footprint block
        depth = 0
        j = start
        while j < len(content):
            if content[j] == '(':
                depth += 1
            elif content[j] == ')':
                depth -= 1
                if depth == 0:
                    break
            j += 1

        fp_block = content[start:j + 1]
        fp_name = fp_match.group(1)

        # 1. Fix FPID: add library prefix if needed
        if ':' not in fp_name and fp_name in FOOTPRINT_SCH_REF_MAP:
            new_fp_name = FOOTPRINT_SCH_REF_MAP[fp_name]
            # Replace just the footprint name in the opening tag
            old_tag = f'(footprint "{fp_name}"'
            new_tag = f'(footprint "{new_fp_name}"'
            fp_block = fp_block.replace(old_tag, new_tag, 1)
            fpid_changes += 1
            print(f"  Fixed FPID: {fp_name} -> {new_fp_name}")

        # 2. Add path if missing
        if '(path ' not in fp_block:
            # Find Reference
            ref_m = re.search(r'\(property "Reference"\s+"([^"]+)"', fp_block)
            if ref_m:
                fp_ref = ref_m.group(1)
                if fp_ref in ref_to_uuid:
                    sym_uuid = ref_to_uuid[fp_ref]
                    # Find the uuid line and add path after it
                    uuid_m = re.search(r'(\(uuid "[^"]+"\))', fp_block)
                    if uuid_m:
                        path_entry = f'\n\t\t(path "/{root_uuid}/{sym_uuid}")'
                        fp_block = fp_block[:uuid_m.end()] + path_entry + fp_block[uuid_m.end():]
                        path_changes += 1
                        print(f"  Added path for {fp_ref}")

        result.append(fp_block)
        i = j + 1

    with open(pcb_path, 'w', encoding='utf-8') as f:
        f.write(''.join(result))

    print(f"\nFPID fixes: {fpid_changes}")
    print(f"Paths added: {path_changes}")
    return fpid_changes, path_changes


def fix_fp_lib_table(table_path):
    """Add missing footprint library entries."""
    with open(table_path, 'r', encoding='utf-8') as f:
        content = f.read()

    changes = 0
    for lib_entry in MISSING_LIBRARIES:
        lib_name = re.search(r'\(name "([^"]+)"', lib_entry).group(1)
        if lib_name not in content:
            # Insert before closing tag
            insert_pos = content.rfind(')')
            if insert_pos >= 0:
                content = content[:insert_pos] + '\n   ' + lib_entry + '\n' + content[insert_pos:]
                changes += 1
                print(f"  Added library: {lib_name}")

    if changes > 0:
        with open(table_path, 'w', encoding='utf-8') as f:
            f.write(content)

    print(f"\nLibrary table entries added: {changes}")
    return changes


if __name__ == "__main__":
    print("=== KiCad Project Fixer v2 ===\n")

    print("Step 1: Parsing schematic...")
    root_uuid, ref_to_uuid = parse_schematic(SCH_FILE)

    print("\nStep 2: Fixing PCB file...")
    fpid_changes, path_changes = fix_pcb(PCB_FILE, root_uuid, ref_to_uuid)

    print("\nStep 3: Fixing fp-lib-table...")
    lib_changes = fix_fp_lib_table(FP_LIB_TABLE)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  FPID fixes: {fpid_changes}")
    print(f"  Paths added: {path_changes}")
    print(f"  Library entries added: {lib_changes}")
    print()
    print("NEXT STEPS:")
    print("1. Open KiCad, load the project")
    print("2. Open the PCB in PCBnew")
    print("3. Press F8 (Update PCB from Schematic)")
    print("4. In the dialog, UNCHECK 'Replace footprints'")
    print("5. CHECK 'Re-link footprints to schematic symbols'")
    print("6. UNCHECK 'Delete unused footprints'")
    print("7. Click 'Update PCB'")

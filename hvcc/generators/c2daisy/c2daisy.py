import jinja2
import os
import shutil
import time
import json2daisy  # type: ignore

from typing import Dict, Optional

from ..copyright import copyright_manager
from . import parameters


hv_midi_messages = {
    "__hv_noteout",
    "__hv_ctlout",
    "__hv_polytouchout",
    "__hv_pgmout",
    "__hv_touchout",
    "__hv_bendout",
    "__hv_midiout",
    "__hv_midioutport"
}


class c2daisy:
    """ Generates a Daisy wrapper for a given patch.
    """

    @classmethod
    def compile(
        cls,
        c_src_dir: str,
        out_dir: str,
        externs: Dict,
        patch_name: Optional[str] = None,
        patch_meta: Optional[Dict] = None,
        num_input_channels: int = 0,
        num_output_channels: int = 0,
        copyright: Optional[str] = None,
        verbose: Optional[bool] = False
    ) -> Dict:

        tick = time.time()

        out_dir = os.path.join(out_dir, "daisy")

        if patch_meta:
            patch_name = patch_meta.get("name", patch_name)
            daisy_meta = patch_meta.get("daisy", {})
        else:
            daisy_meta = {}

        board = daisy_meta.get("board", "pod")

        copyright_c = copyright_manager.get_copyright_for_c(copyright)
        # copyright_plist = copyright or u"Copyright {0} Enzien Audio, Ltd." \
        #     " All Rights Reserved.".format(datetime.datetime.now().year)

        try:
            # ensure that the output directory does not exist
            out_dir = os.path.abspath(out_dir)
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir)

            # copy over static files
            shutil.copytree(os.path.join(os.path.dirname(__file__), "static"), out_dir)

            # copy over generated C source files
            source_dir = os.path.join(out_dir, "source")
            shutil.copytree(c_src_dir, source_dir)

            if daisy_meta.get('board_file'):
                header, board_info = json2daisy.generate_header_from_file(daisy_meta['board_file'])
            else:
                header, board_info = json2daisy.generate_header_from_name(board)

            # remove heavy out params from externs
            externs['parameters']['out'] = [
                t for t in externs['parameters']['out'] if not any(x == y for x in hv_midi_messages for y in t)]

            component_glue = parameters.parse_parameters(
                externs['parameters'], board_info['components'], board_info['aliases'], 'hardware')
            component_glue['class_name'] = board_info['name']
            component_glue['patch_name'] = patch_name
            component_glue['header'] = f"HeavyDaisy_{patch_name}.hpp"
            component_glue['max_channels'] = board_info['channels']
            component_glue['num_output_channels'] = num_output_channels
            component_glue['has_midi'] = board_info['has_midi']
            component_glue['debug_printing'] = daisy_meta.get('debug_printing', False)
            component_glue['usb_midi'] = daisy_meta.get('usb_midi', False)

            # samplerate
            samplerate = daisy_meta.get('samplerate', 48000)
            if samplerate >= 96000:
                component_glue['samplerate'] = 96000
            elif samplerate >= 48000:
                component_glue['samplerate'] = 48000
            elif samplerate >= 32000:
                component_glue['samplerate'] = 32000
            elif samplerate >= 16000:
                component_glue['samplerate'] = 16000
            else:
                component_glue['samplerate'] = 8000

            # blocksize
            blocksize = daisy_meta.get('blocksize')
            if blocksize:
                component_glue['blocksize'] = max(min(256, blocksize), 1)
            else:
                component_glue['blocksize'] = None

            component_glue['copyright'] = copyright_c

            daisy_h_path = os.path.join(source_dir, f"HeavyDaisy_{patch_name}.hpp")
            with open(daisy_h_path, "w") as f:
                f.write(header)

            loader = jinja2.FileSystemLoader(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
            env = jinja2.Environment(loader=loader, trim_blocks=True, lstrip_blocks=True)
            daisy_cpp_path = os.path.join(source_dir, f"HeavyDaisy_{patch_name}.cpp")

            rendered_cpp = env.get_template('HeavyDaisy.cpp').render(component_glue)
            with open(daisy_cpp_path, 'w') as f:
                f.write(rendered_cpp)

            makefile_replacements = {'name': patch_name}
            makefile_replacements['linker_script'] = daisy_meta.get('linker_script', '')
            if makefile_replacements['linker_script'] != '':
                makefile_replacements['linker_script'] = daisy_meta["linker_script"]

            # libdaisy path
            path = daisy_meta.get('libdaisy_path', 2)
            if isinstance(path, int):
                makefile_replacements['libdaisy_path'] = f'{"../" * path}libdaisy'
            elif isinstance(path, str):
                makefile_replacements['libdaisy_path'] = path

            makefile_replacements['bootloader'] = daisy_meta.get('bootloader', '')
            makefile_replacements['debug_printing'] = daisy_meta.get('debug_printing', False)

            rendered_makefile = env.get_template('Makefile').render(makefile_replacements)
            with open(os.path.join(source_dir, "Makefile"), "w") as f:
                f.write(rendered_makefile)

            # ======================================================================================

            return {
                "stage": "c2daisy",
                "notifs": {
                    "has_error": False,
                    "exception": None,
                    "warnings": [],
                    "errors": []
                },
                "in_dir": c_src_dir,
                "in_file": "",
                "out_dir": out_dir,
                "out_file": os.path.basename(daisy_h_path),
                "compile_time": time.time() - tick
            }

        except Exception as e:
            return {
                "stage": "c2daisy",
                "notifs": {
                    "has_error": True,
                    "exception": e,
                    "warnings": [],
                    "errors": [{
                        "enum": -1,
                        "message": str(e)
                    }]
                },
                "in_dir": c_src_dir,
                "in_file": "",
                "out_dir": out_dir,
                "out_file": "",
                "compile_time": time.time() - tick
            }

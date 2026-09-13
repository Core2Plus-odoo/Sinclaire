# Module template

Copy this directory to `addons/sinclaire_<feature>/`, then:

1. Rename the placeholders in `__manifest__.py.tpl` and save it as `__manifest__.py`.
2. Rename `models/model_name.py` after the model it defines.
3. Add an access line per model to `security/ir.model.access.csv`.
4. Delete the directories you do not need — empty ones only add noise.

The files here end in `.tpl` so that Odoo's module loader and this repo's
manifest validator ignore the template itself.

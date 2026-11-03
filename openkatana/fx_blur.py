"""After Effects' Blur & Sharpen effects (web/fx_blur.js): validation of the pack's timeline fields."""

# effect name -> its fields, space separated (unknown fields are rejected before validate runs)
SPECS = {}


def validate(name, p, where):
    """Check one effect's parameters; raise ContractError with the field path on a bad value."""

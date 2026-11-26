# Flash the new firmware image to the EVB

Example for `python -m agentteam run --task examples/flash.example.md --repo <target> --allow-flash`.
The flash stage never executes anything: it prints a plan for a human.

## Context

Board: `<board-name>`, SoC: `<soc>`, image built at `out/<image>.bin`.
Transport: UART console plus a vendor download tool. No JTAG attached.

## What to do

1. Read the repository's flashing notes (`docs/`, `scripts/`) and the build
   output layout.
2. Work out the preconditions, the exact command, how to verify the new image
   booted, and how to roll back to the previous image.
3. Flag anything the task does not tell you — pin state, partition offsets,
   signature requirements — as a warning with a placeholder instead of a guess.

## Do not

- Do not run the flash command.
- Do not open the serial port.
- Do not propose disabling signature checks or write protection.

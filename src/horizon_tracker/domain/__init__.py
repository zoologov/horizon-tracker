"""Domain layer: pure decision cores (schedule windows, calendar verdicts, session state).

No I/O lives here. Everything in this package is deterministic and unit-testable
without a browser, a network or a clock other than the one passed in.
"""

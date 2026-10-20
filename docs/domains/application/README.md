# Application

Use cases of horizon-tracker. A use case orders domain decisions and port calls;
it owns no transport and no browser detail.

## Source

`src/horizon_tracker/application/`

## Use cases

- morning check-in: open the desktop so the Windows logon is recorded, then disconnect
- evening check-out: reconnect and log off

## Features

(none yet — added as the work lands)

## Dependencies

- Depends on: `domain`
- Used by: `cli`

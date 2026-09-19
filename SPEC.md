SurePet Curfew Home Assistant plugin

This plugin should expose a couple of accessories to HA that will help control SurePet flap door.

Settings
- username
- password
- curfew start time
- curfew end time
- curfew override time (e.g. 30 minutes)

Operating principle
Exposes two accessories for each SureFlap in the account: lock and curfew switch

Lock
- shows current effective door lock state, locked or unlocked
- when locking or unlocking should follow curfew-specific logic:
    - outside of curfew time locking the door should lock only until curfew start time - then the door should return to curfew mode
    - inside curfew time unlocking the door should unlock for "curfew override time" e.g. I want to let my cat out, but only for 30 minutes, after that the door should return to normal operation mode

Curfew switch
- on by default
- when on means we're maintaing curfew schedule no matter what, when off we're fully in manual lock mode

Caveats
The app should always maintain and preserve desired state of the door and occasionally check the door is still in desired state (e.g. when batteries are replaced it will lose any state on the device). Curfew mode should be driven by internal Curfew feature of the door. The door has somewhat unreliable connection so when say you're trying to lock the door it needs to have some retry logic on the API.

Testing
We need to local HA instance.

Underlying library
https://github.com/benleb/surepy

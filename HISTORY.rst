=======
History
=======

Unreleased
----------

Features
~~~~~~~~

- Add room acoustic parameter calculation as a fallback step in the simulation task, for methods that don't return the parameters themselves (#140)
- Propagate error messages from simulation methods to the database, distinguishing method-raised, unexpected and container-level errors (#107)
- Add general auralization: generalized *.wav export and a simplified mono-aural auralization based on convolution with the RIR (#90)
- Add logging of Docker container output to the local executor (#101)
- Persist material categories in the database instead of browser storage (#116)
- Add full example projects and models (#113)
- Add user preferences (#110)
- Add endpoint to update material data, with a ``source`` field distinguishing factory from user-created materials (#53)
- Add audio deletion endpoint (#54)
- Add endpoint to retrieve the original (non-convolved) audio file (#58)
- Add model image upload and storage, with cleanup on model/project deletion (#57)
- Add communication between the backend and simulation backends (#61)
- Add SSH passphrase support (#73)

Bug Fixes
~~~~~~~~~

- Ensure the result container is opened when calculating room acoustic parameters, fixing an empty container for DE results (#142)
- Raise an exception in the simulation runner if output data is missing instead of silently creating an empty room impulse response (#139)
- Update material category tests to use ``MaterialCategory`` and ``categoryId`` (#133)
- Replace sinc resampling interpolation with linear interpolation for the energy decay and energy time curves (#122)
- Extract the sampling rate from the EDC time intervals and warn if it isn't uniformly sampled (#117)
- Fall back to the sampling rate defined in the auralization settings instead of a hard-coded value (#118)
- Fix 3DM & Geo conversion producing unneeded triangle surfaces (#103)
- Fix ``/simulations/:id`` endpoint response inconsistency (#105)
- Normalize the signal after convolution to prevent clipping in mono-aural auralization (#95)
- Re-enable removal of Docker containers after execution (#92)
- Change misleading error-level log about available methods to info level (#97)
- Fix updating projects and models, and parameter export acronyms (#56, #59)
- Add missing ``math`` import in the geometry service (#48)
- Update property names in test configs after a rename (#50)

Maintenance
~~~~~~~~~~~

- Reduce Gmsh log verbosity to errors & warnings (#111)
- Clean up executors and simulation service code style (#109)
- Remove broken example geometry files (#108) and the obsolete ``load_test.py`` (#134)
- Move dependencies to ``pyproject.toml``, remove sub-dependencies and group dev/docs dependencies (#34, #127)
- Remove the obsolete Flask-Script dependency (#126)
- Install acousticDE via PyPI instead of a git commit (#125)
- Add Python 3.12/3.13 to supported and tested versions (#87)
- Add the git commit ID to Docker containers and only publish from main (#99)
- Add API documentation for the services module (#89) and clean up docs for removed simulation backends (#88)
- Update developer guidelines to no longer require git submodules for simulation methods (#60)
- Remove outdated linter config for black/isort/flake8 and related pre-commit hooks (#77)
- Various CI fixes: mocked simulation-method config fixture, skip outdated/heavier-setup tests, explicit pipeline failures, ignore unrelated logger.info calls in tests (#124, #128, #130, #84, #85, #79, #78)
- Merge accumulated backend work from the EngD group projects (#46, #33, #67, #93, #98)

0.1.0 (2025-11-05)
------------------

Initial version used at ASSA 2025

Welcome to the CHORAS backend documentation
=================================================
----

This is the backend implementation documentation for the Community Hub for Open-source Room Acoustics Software (CHORAS).

CHORAS is a platform that intends to connect developers, researchers and users in the room acoustics community. We believe that a community platform like CHORAS will increase the impact of our collective work, by bridging the gap between powerful room acoustics simulators on the one hand, and other researchers and end users on the other.

The software currently uses the `Acoustic Diffusion Equation (DE) Method <https://github.com/Building-acoustics-TU-Eindhoven/Diffusion>`_ and `Discontinuous Galerkin (DG) Method <https://github.com/Building-acoustics-TU-Eindhoven/edg-acoustics>`_ as sub-modules for modeling of sound behaviour in complex geometrical spaces. In the near future, we intend to couple other simulation methods to the CHORAS backend, creating a platform that makes various room acoustics simulation methods easily accessible and allows for effortless comparison between these.

Please follow the steps provided here to setup the CHORAS backend.

.. toctree::
   :maxdepth: 1
   :caption: Setup Instructions

   includes/setup.rst

.. toctree::
   :maxdepth: 1
   :caption: Contribution Guidelines

   includes/contributing.rst

.. toctree::
   :maxdepth: 1
   :caption: API Reference

   includes/api_documentation.rst

.. toctree::
   :maxdepth: 1
   :caption: Example Gallery

   auto_examples/index

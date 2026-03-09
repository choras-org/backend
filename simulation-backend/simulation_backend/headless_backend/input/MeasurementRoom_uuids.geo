Point(1) = { 0.0, 0.0, 0.0, 1.0 };
Point(2) = { 0.0, 0.0, 3.3, 1.0 };
Point(3) = { 0.0, 5.1, 0.0, 1.0 };
Point(4) = { 0.0, 5.1, 3.3, 1.0 };
Point(5) = { 5.52, 0.0, 0.0, 1.0 };
Point(6) = { 5.52, 0.0, 3.3, 1.0 };
Point(7) = { 6.21, 4.0, 0.0, 1.0 };
Point(8) = { 6.21, 4.0, 3.3, 1.0 };

Line(1) = { 3, 7 };
Line(2) = { 5, 7 };
Line(3) = { 1, 5 };
Line(4) = { 1, 3 };
Line(5) = { 4, 8 };
Line(6) = { 7, 8 };
Line(7) = { 3, 4 };
Line(8) = { 2, 6 };
Line(9) = { 6, 8 };
Line(10) = { 2, 4 };
Line(11) = { 1, 2 };
Line(12) = { 5, 6 };

Line Loop(1) = { 1, -2, -3, 4 };
Line Loop(2) = { 5, -6, -1, 7 };
Line Loop(3) = { 8, 9, -5, -10 };
Line Loop(4) = { -8, -11, 3, 12 };
Line Loop(5) = { 10, -7, -4, 11 };
Line Loop(6) = { 2, 6, -9, -12 };

Plane Surface(1) = { 1 };
Plane Surface(2) = { 2 };
Plane Surface(3) = { 3 };
Plane Surface(4) = { 4 };
Plane Surface(5) = { 5 };
Plane Surface(6) = { 6 };

Surface Loop(1) = { 1, 2, 3, 4, 5, 6 };
Physical Surface("037fa4d1-c674-4040-8770-0716314f1125") = { 1 };
Physical Surface("cdd912c3-644f-44e1-959a-2464e06cda72") = { 2 };
Physical Surface("73166b3b-0435-4d7f-ad2d-618342366aa8") = { 3 };
Physical Surface("1b11c8f0-31d3-47d0-8463-f57545525c6e") = { 4 };
Physical Surface("5fb4949a-16ab-47b6-8ab3-c9f51c324f77") = { 5 };
Physical Surface("34f916ff-e48e-4faf-a636-d50ba2196464") = { 6 };
Volume(1) = { 1 };
Physical Volume("RoomVolume") = { 1 };
Physical Line("default") = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 };
Mesh.Algorithm = 6;
Mesh.Algorithm3D = 1; // Delaunay3D, works for boundary layer insertion.
Mesh.Optimize = 1; // Gmsh smoother, works with boundary layers (netgen version does not).
Mesh.CharacteristicLengthFromPoints = 1;
// Recombine Surface "*";

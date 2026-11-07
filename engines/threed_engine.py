"""Lightweight 3D mesh utilities and OBJ/STL/ASCII-PLY loaders for Kivy."""
import math
import os
import struct


class ThreeDEngine:
    def __init__(self):
        self.active_model_path = None
        self.active_shape = "cube"
        self.model_stats = {}
        self.vertices = []
        self.faces = []
        self.rotation = [0.0, 0.0, 0.0]
        self.load_cube()

    @property
    def mesh_vertices(self):
        return self.vertices

    @property
    def mesh_faces(self):
        return self.faces

    def load_cube(self):
        self.active_shape = "cube"
        self.vertices = [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]]
        self.faces = [[0,1,2,3],[4,7,6,5],[0,4,5,1],[1,5,6,2],[2,6,7,3],[3,7,4,0]]
        self._stats("Laiba_Cube", "INTERNAL")
        return self.model_stats

    def load_pyramid(self):
        self.active_shape = "pyramid"
        self.vertices = [[-1,-1,-1],[1,-1,-1],[1,-1,1],[-1,-1,1],[0,1,0]]
        self.faces = [[0,3,2,1],[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        self._stats("Laiba_Pyramid", "INTERNAL")
        return self.model_stats

    def _stats(self, name, fmt):
        self.model_stats = {"file": name, "format": fmt, "vertices": len(self.vertices), "faces": len(self.faces)}

    def load_model(self, filepath):
        if not os.path.isfile(filepath):
            return {"status": "error", "message": "File not found: {}".format(filepath)}
        ext = os.path.splitext(filepath)[1].lower()
        try:
            if ext == ".obj":
                self._parse_obj(filepath)
            elif ext == ".stl":
                self._parse_stl(filepath)
            elif ext == ".ply":
                self._parse_ascii_ply(filepath)
            elif ext in (".gltf", ".glb"):
                return {"status": "error", "message": "GLTF/GLB parsing is not implemented; file was not falsely accepted."}
            else:
                return {"status": "error", "message": "Unsupported 3D format: {}".format(ext)}
            self.active_model_path = filepath
            self.active_shape = "custom"
            self._stats(os.path.basename(filepath), ext[1:].upper())
            return {"status": "success", "stats": dict(self.model_stats)}
        except Exception as exc:
            return {"status": "error", "message": "Could not parse model: {}".format(exc)}

    def _parse_obj(self, path):
        vertices, faces = [], []
        with open(path, encoding="utf-8", errors="replace") as stream:
            for line in stream:
                parts = line.strip().split()
                if not parts or parts[0].startswith("#"):
                    continue
                if parts[0] == "v" and len(parts) >= 4:
                    vertices.append([float(v) for v in parts[1:4]])
                elif parts[0] == "f" and len(parts) >= 4:
                    face = []
                    for item in parts[1:]:
                        index = int(item.split("/")[0])
                        face.append(index - 1 if index > 0 else len(vertices) + index)
                    if all(0 <= i < len(vertices) for i in face):
                        faces.append(face)
        if not vertices or not faces:
            raise ValueError("OBJ contains no usable vertices/faces")
        self.vertices, self.faces = vertices, faces

    def _parse_stl(self, path):
        size = os.path.getsize(path)
        with open(path, "rb") as stream:
            header = stream.read(84)
            if len(header) < 84:
                raise ValueError("STL file is truncated")
            count = struct.unpack("<I", header[80:84])[0]
            if 84 + count * 50 == size:
                vertices, faces, lookup = [], [], {}
                def index_for(v):
                    key = tuple(round(x, 7) for x in v)
                    if key not in lookup:
                        lookup[key] = len(vertices); vertices.append(list(v))
                    return lookup[key]
                for _ in range(count):
                    record = stream.read(50)
                    if len(record) != 50: raise ValueError("Truncated binary STL triangle")
                    values = struct.unpack("<12fH", record)
                    faces.append([index_for(values[3:6]), index_for(values[6:9]), index_for(values[9:12])])
                self.vertices, self.faces = vertices, faces
            else:
                stream.seek(0)
                text = stream.read().decode("ascii", errors="ignore")
                vertices, faces, lookup, current = [], [], {}, []
                for line in text.splitlines():
                    p = line.strip().split()
                    if len(p) == 4 and p[0].lower() == "vertex":
                        v = tuple(round(float(x), 7) for x in p[1:4])
                        if v not in lookup: lookup[v] = len(vertices); vertices.append(list(v))
                        current.append(lookup[v])
                        if len(current) == 3: faces.append(current); current = []
                self.vertices, self.faces = vertices, faces
        if not self.vertices or not self.faces: raise ValueError("STL contains no triangles")

    def _parse_ascii_ply(self, path):
        with open(path, encoding="ascii", errors="replace") as stream:
            if stream.readline().strip() != "ply": raise ValueError("Invalid PLY header")
            vertex_count = face_count = 0
            ascii_format = False
            while True:
                line = stream.readline()
                if not line: raise ValueError("Incomplete PLY header")
                p = line.strip().split()
                if p[:2] == ["format", "ascii"]: ascii_format = True
                if len(p) == 3 and p[:2] == ["element", "vertex"]: vertex_count = int(p[2])
                if len(p) == 3 and p[:2] == ["element", "face"]: face_count = int(p[2])
                if p and p[0] == "end_header": break
            if not ascii_format: raise ValueError("Only ASCII PLY is supported")
            vertices = [[float(x) for x in stream.readline().split()[:3]] for _ in range(vertex_count)]
            faces = []
            for _ in range(face_count):
                row = [int(x) for x in stream.readline().split()]
                if row and row[0] >= 3: faces.append(row[1:1 + row[0]])
        if not vertices or not faces: raise ValueError("PLY contains no usable mesh")
        self.vertices, self.faces = vertices, faces

    def rotate(self, dx=0, dy=0, dz=0):
        self.rotation[0] = (self.rotation[0] + dx) % 360
        self.rotation[1] = (self.rotation[1] + dy) % 360
        self.rotation[2] = (self.rotation[2] + dz) % 360
        return tuple(self.rotation)

    def get_projected_wireframe(self, angle_x=None, angle_y=None, scale=60, center_x=120, center_y=120):
        ax = math.radians(self.rotation[0] if angle_x is None else angle_x)
        ay = math.radians(self.rotation[1] if angle_y is None else angle_y)
        az = math.radians(self.rotation[2])
        projected = []
        for x, y, z in self.vertices:
            x, y = x * math.cos(az) - y * math.sin(az), x * math.sin(az) + y * math.cos(az)
            x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
            y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
            depth = 4 + z
            factor = scale / max(0.2, depth)
            projected.append((int(center_x + x * factor), int(center_y - y * factor)))
        lines = []
        for face in self.faces:
            for i, idx in enumerate(face):
                nxt = face[(i + 1) % len(face)]
                if 0 <= idx < len(projected) and 0 <= nxt < len(projected):
                    lines.append((projected[idx], projected[nxt]))
        return lines

    def load_file(self, filepath):
        return self.load_model(filepath)

    def render_to_canvas(self, canvas, width=320, height=270):
        canvas.delete("all")
        lines = self.get_projected_wireframe(scale=min(width, height) * 0.65,
            center_x=width / 2, center_y=height / 2)
        for start, end in lines:
            canvas.create_line(start[0], start[1], end[0], end[1], fill="#00E5FF", width=2)
        return self.model_stats

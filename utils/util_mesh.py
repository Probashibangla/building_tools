import bpy
import bmesh
import operator
import functools as ft
from mathutils import Matrix, Vector
from bmesh.types import BMVert


def get_edit_mesh():
    """ Get editmode mesh """
    return bpy.context.edit_object.data

def make_mesh(name):
    """ Make new mesh data """
    return bpy.data.meshes.new(name)

def select(elements, val=True):
    """ For each item in elements set select to val """
    for el in elements:
        el.select = val

def filter_geom(geom, _type):
    """ Find all elements of type _type in geom iterable """
    return list(filter(lambda x: isinstance(x, _type), geom))

def filter_vertical_edges(edges, normal):
    """ Determine edges that are vertical based on a normal value """
    res = []
    rnd = lambda val: round(val, 4)

    for e in edges:
        if normal.z:
            s = set([rnd(v.co.x) for v in e.verts])
        elif normal.y:
            s = set([rnd(v.co.x) for v in e.verts])
        else:
            s = set([rnd(v.co.y) for v in e.verts])
        if len(s) == 1:
            res.append(e)
    return res

def filter_horizontal_edges(edges, normal):
    """ Determine edges that are horizontal based on a normal value """
    res = []
    rnd = lambda val: round(val, 4)

    for e in edges:
        if normal.z:
            s = set([rnd(v.co.y) for v in e.verts])
        elif normal.y:
            s = set([rnd(v.co.z) for v in e.verts])
        else:
            s = set([rnd(v.co.z) for v in e.verts])
        if len(s) == 1:
            res.append(e)
    return res

def calc_edge_median(edge):
    """ Calculate the center position of edge """
    return ft.reduce(operator.add, [v.co for v in edge.verts])/len(edge.verts)

def calc_verts_median(verts):
    """ Determine the median position of verts """
    return ft.reduce(operator.add, [v.co for v in verts])/len(verts)

def calc_face_dimensions(face):
    """ Determine the width and height of face """
    if face.normal.x and not face.normal.y:
        width = max([v.co.y for v in face.verts]) - \
            min([v.co.y for v in face.verts])
    elif face.normal.y and not face.normal.x:
        width = max([v.co.x for v in face.verts]) - \
            min([v.co.x for v in face.verts])
    elif face.normal.x and face.normal.y:
        v1 = max([v.co for v in face.verts], key=lambda v: v.x)
        v2 = min([v.co for v in face.verts], key=lambda v: v.x)
        width = (v1 - v2).length
    else:
        width = 0

    height = max([v.co.z for v in face.verts]) - \
        min([v.co.z for v in face.verts])
    return width, height

def calc_edge_orient(edge):
    """ Determine the orientation of edge """
    x_coords = list(set([round(v.co.x, 1) for v in edge.verts]))
    y_coords = list(set([round(v.co.y, 1) for v in edge.verts]))
    z_coords = list(set([round(v.co.z, 1) for v in edge.verts]))

    if len(x_coords) == 1 or len(y_coords) == 1:
        return Vector((0, 0, 1))
    elif len(z_coords) == 1 and len(y_coords) == 1:
        return Vector((1, 0, 0))
    elif len(z_coords) == 1 and len(x_coords) == 1:
        return Vector((0, 1, 0))
    else:
        return Vector((0, 0, 0))

def square_face(bm, face):
    """ Make face square if it is rectangular """
    max_length = max([e.calc_length() for e in face.edges])
    min_length = min([e.calc_length() for e in face.edges])

    scale_factor = max_length / min_length
    min_edge = list(filter(lambda e: e.calc_length() == min_length,
                           face.edges))[-1]

    if calc_edge_orient(min_edge) == Vector((1, 0, 0)):
        scale_vec = (scale_factor, 1, 1)
    elif calc_edge_orient(min_edge) == Vector((0, 1, 0)):
        scale_vec = (1, scale_factor, 1)
    elif calc_edge_orient(min_edge) == Vector((0, 0, 1)):
        scale_vec = (1, 1, scale_factor)
    else:
        scale_vec = (1, 1, 1)

    fc = face.calc_center_median()
    bmesh.ops.scale(bm, verts=list(face.verts), vec=scale_vec,
                    space=Matrix.Translation(-fc))
    return scale_factor

def face_with_verts(bm, verts, default=None):
    """ Find a face in the bmesh with the given verts"""
    for face in bm.faces:
        if len(set(list(face.verts) + verts)) == len(verts):
            return face
    return default

def split_quad(vertical=False, cuts=4):
    """ Subdivide a quad's edges into even horizontal/vertical cuts """
    me = get_edit_mesh()
    bm = bmesh.from_edit_mesh(me)

    # Find selected faces
    faces = [f for f in bm.faces if f.select]

    for face in faces:
        if vertical:
            e = filter_horizontal_edges(face.edges, face.normal)
            res = bmesh.ops.subdivide_edges(bm, edges=e, cuts=cuts)
        else:
            e = filter_vertical_edges(face.edges, face.normal)
            res = bmesh.ops.subdivide_edges(bm, edges=e, cuts=cuts)

    bmesh.update_edit_mesh(me, True)
    return res

def split(bm, face, svertical, shorizontal, offx=0, offy=0, offz=0):
    """ Split a quad into regular quad sections (basically an inset with only right-angled edges) """

    # scale svertical and shorizontal
    scale       = 3
    svertical   *= scale
    shorizontal *= scale

    do_vertical     = svertical < scale
    do_horizontal   = shorizontal < scale

    face.select = False
    median = face.calc_center_median()

    # SKIP BOTH
    # `````````
    if not do_horizontal and not do_vertical:
        return face

    if do_horizontal:
        # Determine horizontal edges
        # --  edges whose verts have similar z coord
        horizontal = list(filter(lambda e: len(
            set([round(v.co.z, 1) for v in e.verts])) == 1, face.edges))
        # Subdivide edges
        sp_res = bmesh.ops.subdivide_edges(bm, edges=horizontal, cuts=2)
        verts = filter_geom(sp_res['geom_inner'], BMVert)

        # Scale subdivide face
        T = Matrix.Translation(-median)
        sv = face.normal.cross(Vector((0, 0, 1)))
        scale_vector = (abs(sv.x) * shorizontal if sv.x else 1, abs(sv.y) * shorizontal if sv.y else 1,
                        abs(sv.z) * shorizontal if sv.z else 1)
        bmesh.ops.scale(bm, vec=scale_vector, verts=verts, space=T)


    if do_vertical:
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts))
        face = face_with_verts(bm, verts) if do_horizontal else face

        # Determine vertical edges
        # -- edges whose verts have similar x/y coord
        other = list(filter(lambda e: len(
            set([round(v.co.z, 1) for v in e.verts])) == 1, face.edges))
        vertical = list(set(face.edges) - set(other))

        # Subdivide
        sp_res = bmesh.ops.subdivide_edges(bm, edges=vertical, cuts=2)
        verts = filter_geom(sp_res['geom_inner'], BMVert)

        # Scale subdivide face
        T = Matrix.Translation(-median)
        bmesh.ops.scale(bm, vec=(1, 1, svertical), verts=verts, space=T)

    # OFFSET VERTS
    # ---------------------
    # -- horizontal offset
    if do_horizontal and do_vertical:
        link_edges = [e for v in verts for e in v.link_edges]
        all_verts = list({v for e in link_edges for v in e.verts})
        bmesh.ops.translate(bm, verts=all_verts, vec=(offx, offy, 0))
    elif do_horizontal and not do_vertical:
        bmesh.ops.translate(bm, verts=verts, vec=(offx, offy, 0))

    # -- vertical offset
    bmesh.ops.translate(bm, verts=verts, vec=(0, 0, offz))

    face = face_with_verts(bm, verts)
    return face

from loop_interpolation import InterpolatorBuilder, InterpolatorType
from loop_common.geometry import BoundingBox

# Define a bounding box for the interpolation domain
bbox = BoundingBox(origin=[0,0,0], maximum=[10,10,10])

# Create an interpolator builder with the desired type and bounding box
builder = InterpolatorBuilder(
    interpolatortype="FDI",
    bounding_box=bbox,
    nelements=100000,
    buffer=0.2,
)

builder.add_value_constraints([[5,5,5,0.]])

builder.add_normal_constraints([[5,5,5,0,0.,1.]])

builder.setup_interpolator()
interpolator = builder.build()

interpolator.solve_system()


interpolator.to_yaml('interpolator.yaml')
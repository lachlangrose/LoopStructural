# ruff: noqa: D102
"""PyVista Trame Viewer class for a Vue 3 client.

This class, derived from `pyvista.trame.ui.base_viewer`,
is intended for use with a trame application where the client type is "vue3".
Therefore, the `ui` method implemented by this class utilizes the API of Vuetify 3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.widgets import vuetify3 as vuetify

import pyvista
from pyvista.trame.ui.vuetify3 import Viewer


if TYPE_CHECKING:  # pragma: no cover
    from trame_client.ui.core import AbstractLayout


class LoopViewer(Viewer):
    def __init__(self, *args, **kwargs):
        """Overwrite the pyvista trame layout to use a singlepage layout
        and add an object visibility menu to the drawer
        """
        super().__init__(*args, **kwargs)

    def make_layout(self, *args, **kwargs) -> AbstractLayout:

        return SinglePageWithDrawerLayout(*args, **kwargs)

    def ui(self, *args, **kwargs):
        with self.layout as layout:
            layout.title.set_text("Loop 2.0 Viewer")
        with self.layout.content:

            return super().ui(*args, **kwargs)

    def toggle_visibility(self, **kwargs):
        """Toggle the visibility of an object in the plotter.
        this is a slot called by the state change, the kwargs are the current state
        so we need to check the keys and update accordingly
        """
        for k in kwargs.keys():
            object_name = k.split("__visibility")[0]
            if object_name in self.plotter.actors:
                self.plotter.actors[object_name].visibility = kwargs[k]
        self.update()
        # self.actors[k].visibility = not self.actors[k].visibility

    def set_opacity(self, **kwargs):
        """Set the opacity of an object in the plotter.
        this is a slot called by the state change, the kwargs are the current state
        so we need to check the keys and update accordingly
        """
        for k in kwargs.keys():
            object_name = k.split("__opacity")[0]
            if object_name in self.plotter.actors:
                self.plotter.actors[object_name].prop.opacity = kwargs[k]
        self.update()
        # self.actors[k].visibility = not self.actors[k].visibility

    def set_active_scalars(self, **kwargs):
        """Set the active scalar array for a tracked object mesh."""
        for k in kwargs.keys():
            object_name = k.split("__active_scalars")[0]
            scalar_name = kwargs[k]
            if scalar_name == "None":
                scalar_name = None
            changed = self.plotter.set_object_active_scalars(object_name, scalar_name)
            actor = self.plotter.actors.get(object_name)
            if not changed or actor is None:
                continue

            mapper = actor.mapper
            dataset = mapper.dataset

            if scalar_name is None:
                dataset.set_active_scalars(None)
                mapper.array_name = None
                mapper.scalar_visibility = False
                continue

            if scalar_name in dataset.point_data:
                dataset.set_active_scalars(scalar_name, preference="point")
                mapper.scalar_map_mode = "point"
            elif scalar_name in dataset.cell_data:
                dataset.set_active_scalars(scalar_name, preference="cell")
                mapper.scalar_map_mode = "cell"

            mapper.array_name = scalar_name
            mapper.scalar_visibility = True
        self.update()

    def set_active_vectors(self, **kwargs):
        """Set the active vector array for a tracked object mesh."""
        for k in kwargs.keys():
            object_name = k.split("__active_vectors")[0]
            vector_name = kwargs[k]
            if vector_name == "None":
                vector_name = None
            self.plotter.set_object_active_vectors(object_name, vector_name)
        self.update()

    def object_menu(self):
        with self.layout.drawer as drawer:
            with vuetify.VCard():

                for k, a in self.plotter.actors.items():
                    if type(a) is not pyvista.plotting.actor.Actor:
                        continue
                    scalar_options = ["None"] + self.plotter.get_object_scalar_options(k)
                    vector_options = ["None"] + self.plotter.get_object_vector_options(k)
                    has_scalar_options = len(scalar_options) > 1
                    has_vector_options = len(vector_options) > 1

                    if k in self.plotter.objects:
                        active_scalar_name = self.plotter.objects[k].active_scalars_name
                        active_vector_name = self.plotter.objects[k].active_vectors_name
                    else:
                        active_scalar_name = None
                        active_vector_name = None

                    drawer.server.state[f"{k}__visibility"] = True
                    drawer.server.state[f"{k}__control_visibility"] = False
                    drawer.server.state[f"{k}__opacity"] = a.prop.opacity
                    drawer.server.state[f"{k}__active_scalars"] = (
                        active_scalar_name if active_scalar_name is not None else "None"
                    )
                    drawer.server.state[f"{k}__active_vectors"] = (
                        active_vector_name if active_vector_name is not None else "None"
                    )
                    drawer.server.state.change(f"{k}__visibility")(self.toggle_visibility)
                    drawer.server.state.change(f"{k}__opacity")(self.set_opacity)
                    drawer.server.state.change(f"{k}__active_scalars")(self.set_active_scalars)
                    drawer.server.state.change(f"{k}__active_vectors")(self.set_active_vectors)
                    with vuetify.VRow(
                        classes='pa-0 ma-0 align-center fill-height',
                        style='flex-wrap: nowrap',
                    ):
                        with vuetify.VCol():

                            vuetify.VCheckbox(
                                label=k,
                                classes="ma-0 pa-0",
                                v_model=(f"{k}__visibility"),
                                # click=(self.toggle_visibility("test")),
                            )
                        with vuetify.VCol():
                            vuetify.VBtn(
                                icon='mdi-dots-horizontal',
                                click=(f'{k}__control_visibility=!{k}__control_visibility'),
                                # click=(self.toggle_visibility("test")),
                            )
                    with vuetify.VCard(classes="ma-0 pa-0", v_show=f'{k}__control_visibility'):

                        with vuetify.VRow(
                            classes="ma-0 pa-0 d-flex align-center",
                        ):

                            vuetify.VSlider(
                                v_model=(f"{k}__opacity"),
                                label="Opacity",
                                min=0,
                                max=1,
                                step=0.1,
                                thumb_label=True,
                            )
                        if has_scalar_options:
                            with vuetify.VRow(
                                classes="ma-0 pa-0 d-flex align-center",
                            ):

                                vuetify.VSelect(
                                    v_model=(f"{k}__active_scalars"),
                                    items=(scalar_options),
                                    label="Scalars",
                                    density="compact",
                                    hide_details=True,
                                )
                        if has_vector_options:
                            with vuetify.VRow(
                                classes="ma-0 pa-0 d-flex align-center",
                            ):

                                vuetify.VSelect(
                                    v_model=(f"{k}__active_vectors"),
                                    items=(vector_options),
                                    label="Vectors",
                                    density="compact",
                                    hide_details=True,
                                )

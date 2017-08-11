#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Project components class.

It is important to not import necessary things at the method level to make
importing this file as fast as possible. Otherwise using the command line
interface feels sluggish and slow. Import things only the functions they are
needed.

:copyright: Lion Krischer (krischer@geophysik.uni-muenchen.de), 2013

:license: GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
from __future__ import absolute_import

import glob
import imp
import inspect
import pathlib
import os
import warnings

from lasif import LASIFError, LASIFNotFoundError, LASIFWarning
import lasif.domain

from .actions import ActionsComponent
from .adjoint_sources import AdjointSourcesComponent
from .communicator import Communicator
from .component import Component
from .downloads import DownloadsComponent
from .events import EventsComponent
from .weights import WeightsComponent
from .iterations import IterationsComponent
from .query import QueryComponent
from .stations import StationsComponent
from .validator import ValidatorComponent
from .visualizations import VisualizationsComponent
from .waveforms import WaveformsComponent
from .windows import WindowsAndAdjointSourcesComponent


class Project(Component):
    """
    A class managing LASIF projects.

    It represents the heart of LASIF.
    """
    def __init__(self, project_root_path: pathlib.Path,
                 init_project: bool=False):
        """
        Upon intialization, set the paths and read the config file.

        :param project_root_path: The root path of the project.
        :param init_project: Determines whether or not to initialize a new
            project, e.g. create the necessary folder structure. If a string is
            passed, the project will be given this name. Otherwise a default
            name will be chosen. Defaults to False.
        """
        # Setup the paths.
        self.__setup_paths(project_root_path.absolute())

        if init_project:
            if not project_root_path.exists():
                os.makedirs(project_root_path)
            self.__init_new_project(init_project)

        if not self.paths["config_file"].exists():
            msg = ("Could not find the project's config file. Wrong project "
                   "path or uninitialized project?")
            raise LASIFError(msg)

        # Setup the communicator and register this component.
        self.__comm = Communicator()
        super(Project, self).__init__(self.__comm, "project")

        self.__setup_components()

        # Finally update the folder structure.
        self.__update_folder_structure()

        self._read_config_file()

        # Functions will be cached here.
        self.__project_function_cache = {}
        self.__copy_fct_templates(init_project=init_project)

    def __str__(self):
        """
        Pretty string representation.
        """
        # Count all files and sizes.
        ret_str = "LASIF project \"%s\"\n" % self.config["project_name"]
        ret_str += "\tDescription: %s\n" % self.config["description"]
        ret_str += "\tProject root: %s\n" % self.paths["root"]
        ret_str += "\tContent:\n"
        ret_str += "\t\t%i events\n" % self.comm.events.count()

        return ret_str

    def __copy_fct_templates(self, init_project):
        """
        Copies the function templates to the project folder if they do not
        yet exist.

        :param init_project: Flag if this is called during the project
            initialization or not. If not called during project initialization
            this function will raise a warning to make users aware of the
            changes in LASIF.
        """
        directory = pathlib.Path(__file__).parent.parent / "function_templates"
        for filename in directory.glob("*.py"):
            new_filename = self.paths["functions"] / filename.name
            if not new_filename.exists():
                if not init_project:
                    warnings.warn(
                        "Function template '{filename.name}' did not exist. "
                        "It does now. Did you update a later LASIF version? "
                        "Please make sure you are aware of the changes.",
                        LASIFWarning)
                import shutil
                shutil.copy(src=filename, dst=new_filename)

    def _read_config_file(self):
        """
        Parse the config file.
        """
        import toml
        with open(self.paths["config_file"], "r") as fh:
            config_dict = toml.load(fh)

        self.config = config_dict["lasif_project"]
        self.solver = config_dict["solver"]
        self.simulation_params = self.solver["settings"]["simulation_parameters"]
        self.preprocessing_params = config_dict["data_preprocessing"]

        self.domain = lasif.domain.ExodusDomain(self.config['mesh_file'])

    def get_communicator(self):
        return self.__comm

    def __setup_components(self):
        """
        Setup the different components of the project. The goal is to
        decouple them as much as possible to keep the structure sane and
        maintainable.

        Communication will happen through the communicator which will also
        keep the references to the single components.
        """
        # Basic components.
        EventsComponent(folder=self.paths["eq_data"], communicator=self.comm,
                        component_name="events")
        WaveformsComponent(data_folder=self.paths["eq_data"], preproc_data_folder=self.paths["preproc_data"],
                           synthetics_folder=self.paths["synthetics"],
                           communicator=self.comm, component_name="waveforms")
        WeightsComponent(weights_folder=self.paths["weights"],
                            communicator=self.comm,
                            component_name="weights")
        IterationsComponent(communicator=self.comm,
                            component_name="iterations")

        # Action and query components.
        QueryComponent(communicator=self.comm, component_name="query")
        VisualizationsComponent(communicator=self.comm,
                                component_name="visualizations")
        ActionsComponent(communicator=self.comm,
                         component_name="actions")
        ValidatorComponent(communicator=self.comm,
                           component_name="validator")

        WindowsAndAdjointSourcesComponent(
            folder=self.paths["adjoint_sources"],
            communicator=self.comm,
            component_name="wins_and_adj_sources")
        # # Window and adjoint source components.
        # WindowsAndAdjointSourcesComponent(
        #     folder=self.paths["windows_and_adjoint_sources"],
        #     communicator=self.comm,
        #     component_name="win_adjoint")
        # AdjointSourcesComponent(ad_src_folder=self.paths["adjoint_sources"],
        #                         communicator=self.comm,
        #                         component_name="adjoint_sources")

        # Data downloading component.
        DownloadsComponent(communicator=self.comm,
                           component_name="downloads")

    def __setup_paths(self, root_path: pathlib.Path):
        """
        Central place to define all paths.
        """
        # Every key containing the string "file" denotes a file, all others
        # should denote directories.
        self.paths = dict()
        self.paths["root"] = root_path

        # Data
        self.paths["data"] = root_path / "DATA"
        self.paths["corr_data"] = root_path / "DATA" / "CORRELATIONS"
        self.paths["eq_data"] = root_path / "DATA" / "EARTHQUAKES"

        self.paths["synthetics"] = root_path / "SYNTHETICS"
        self.paths["corr_synthetics"] = root_path / "SYNTHETICS" / "CORRELATIONS"
        self.paths["eq_synthetics"] = root_path / "SYNTHETICS" / "EARTHQUAKES"

        self.paths["preproc_data"] = root_path / "PREPROCESSED_DATA"
        self.paths["preproc_eq_data"] = root_path / "PREPROCESSED_DATA" / "EARTHQUAKES"
        self.paths["preproc_corr_data"] = root_path / "PREPROCESSED_DATA" / "CORRELATIONS"

        self.paths["sets"] = root_path / "SETS"
        self.paths["windows"] = root_path / "SETS" / "WINDOWS"
        self.paths["weights"] = root_path / "SETS" / "WEIGHTS"

        self.paths["adjoint_sources"] = root_path / "ADJOINT_SOURCES"
        self.paths["output"] = root_path / "OUTPUT"
        self.paths["logs"] = root_path / "OUTPUT" / "LOGS"
        self.paths["salvus_input"] = root_path / "SALVUS_INPUT_FILES"

        # Path for the custom functions.
        self.paths["functions"] = root_path / "FUNCTIONS"

        # Paths for various files.
        self.paths["config_file"] = root_path / "lasif_config.toml"

    def __update_folder_structure(self):
        """
        Updates the folder structure of the project.
        """
        for name, path in self.paths.items():
            if "file" in name or path.exists():
                continue
            os.makedirs(path)

    def __init_new_project(self, project_name):
        """
        Initializes a new project. This currently just means that it creates a
        default config file. The folder structure is checked and rebuilt every
        time the project is initialized anyways.
        """
        if not project_name:
            project_name = "LASIFProject"

        lasif_config_str = f"# Please fill in this config file before proceeding with using LASIF \n \n" \
                           f"[lasif_project]\n" \
                           f"  project_name = \"{project_name}\"\n" \
                           f"  description = \"\"\n" \
                           f"  mesh_file = \"\"\n\n" \
                           f"  [lasif_project.download_settings]\n" \
                           f"    seconds_before_event = 300.0\n" \
                           f"    seconds_after_event = 3600.0\n" \
                           f"    interstation_distance_in_meters = 1000.0\n" \
                           f"    channel_priorities = [ \"BH[Z,N,E]\", \"LH[Z,N,E]\", \"HH[Z,N,E]\", \"EH[Z,N,E]\", \"MH[Z,N,E]\",]\n" \
                           f"    location_priorities = [ \"\", \"00\", \"10\", \"20\", \"01\", \"02\",]\n" \
                           f"\n"

        data_preproc_str = f"[data_preprocessing]\n" \
                           f"  highpass_period = 30.0\n" \
                           f"  lowpass_period = 50.0\n" \
                           f"\n"

        solver_par_str = "[solver]\n" \
                     "  name = \"Salvus\"\n\n" \
                     "  [solver.settings]\n" \
                     "    adjoint_source_time_shift = -10\n\n" \
                     "    [solver.settings.simulation_parameters]\n" \
                     "      number_of_time_steps = 2000\n" \
                     "      sampling_rate = 20.0\n" \
                     "      time_increment = 0.1\n" \
                     "      end_time = 2700.0\n" \
                     "      start_time = -10.0\n" \
                     "      source_center_frequency = 0.025\n" \
                     "      polynomial_order = 4\n" \
                     "      dimensions = 3\n\n" \
                     "    [solver.settings.computational_setup]\n" \
                     "      number_of_processors = 4\n" \
                     "      salvus_call = \"mpirun -n 4 salvus_bin\"\n\n"

        lasif_config_str += data_preproc_str + solver_par_str

        with open(self.paths["config_file"], "w") as fh:
            fh.write(lasif_config_str)

    def get_project_function(self, fct_type):
        """
        Helper importing the project specific function.

        :param fct_type: The desired function.
        """
        # Cache to avoid repeated imports.
        if fct_type in self.__project_function_cache:
            return self.__project_function_cache[fct_type]

        # type / filename map
        fct_type_map = {
            "window_picking_function": "window_picking_function.py",
            "preprocessing_function": "preprocessing_function.py",
            "preprocessing_function_asdf": "preprocessing_function_asdf.py",
            "process_synthetics": "process_synthetics.py",
            "source_time_function": "source_time_function.py"
        }

        if fct_type not in fct_type:
            msg = "Function '%s' not found. Available types: %s" % (
                fct_type, str(list(fct_type_map.keys())))
            raise LASIFNotFoundError(msg)

        filename = os.path.join(self.paths["functions"],
                                fct_type_map[fct_type])
        if not os.path.exists(filename):
            msg = "No file '%s' in existence." % filename
            raise LASIFNotFoundError(msg)

        fct_template = imp.load_source("_lasif_fct_template", filename)

        try:
            fct = getattr(fct_template, fct_type)
        except AttributeError:
            raise LASIFNotFoundError("Could not find function %s in file '%s'"
                                     % (fct_type, filename))

        if not callable(fct):
            raise LASIFError("Attribute %s in file '%s' is not a function."
                             % (fct_type, filename))

        # Add to cache.
        self.__project_function_cache[fct_type] = fct
        return fct

    def get_output_folder(self, type, tag):
        """
        Generates a output folder in a unified way.

        :param type: The type of data. Will be a subfolder.
        :param tag: The tag of the folder. Will be postfix of the final folder.
        """
        from obspy import UTCDateTime
        d = str(UTCDateTime()).replace(":", "-").split(".")[0]

        output_dir = os.path.join(self.paths["output"], type.lower(),
                                  "%s__%s" % (d, tag))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        return output_dir

    def get_log_file(self, log_type, description):
        """
        Returns the name of a log file. It will create all necessary
        directories along the way but not the log file itsself.

        :param log_type: The type of logging. Will result in a subfolder.
            Examples for this are ``"PROCESSING"``, ``"DOWNLOADS"``, ...
        :param description: Short description of what is being downloaded.
            Will be used to derive the name of the logfile.
        """
        from obspy import UTCDateTime
        log_dir = os.path.join(self.paths["logs"], log_type)
        filename = ("%s___%s" % (str(UTCDateTime()), description))
        filename += os.path.extsep + "log"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        return os.path.join(log_dir, filename)

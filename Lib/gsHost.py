#!/usr/bin/env python

"""
A file-like object to access a host file, the single entry point
to an entire gridspec data file layout.

Dave Kindig and Alex Pletzer, Tech-X (2011)
This code is provided with the hope that it will be useful.
No guarantee is provided whatsoever. Use at your own risk.
"""

from __future__ import print_function
from ctypes import c_char_p, c_int, CDLL, byref
import cdms2
from cdms2.error import CDMSError
from cdms2.gsStaticVariable import StaticFileVariable
from cdms2.gsTimeVariable import TimeFileVariable
from six import string_types

LIBCF = 'libcf'
try:
    from pycf import libCFConfig, __path__
    LIBCF = __path__[0] + '/pylibcf'

except BaseException:
    print('Error: could not import pycf')


def open(hostfile, mode='r'):
    """
    Open host file

    Parameters
    ----------
    hostfile : host file
    mode : valid cdms2 open file mode
    """

    outHostFile = Host(hostfile, mode)
    return outHostFile


class Host:
    """
    A LibCF/GRIDSPEC host file object. This acts as the single point of entry to
    a GRIDSPEC aggregation. Variables and grids can be requested solely through
    the Host object, which is a hybrid between a variable and file object.
    Host relies on the libcf shared object. As such, if there is a problem
    consult http://www.unidata.ucar.edu/software/libcf/docs/libcf/ for details
    on building host files and all related GRIDSPEC files.
    """

    def __init__(self, hostfile, mode='r'):
        """
        Constructor

        Parameters
        ----------

        hostfile : path to the host
        mode : read only at the moment
        """

        self.__initialize()
        self.uri = hostfile
        self.mode = mode

        # Data dir based on location of hostfile
        if mode != 'r':
            raise CDMSError('Only read mode is supported for host file')

        for sosuffix in '.so', '.dylib', '.dll', '.a':
            self.libcfdll = CDLL(LIBCF + sosuffix)
            if self.libcfdll:
                break

        if self.libcfdll is None:
            raise CDMSError('libcf not installed or incorrect path\n  ')

        libcfdll = self.libcfdll

        status = libcfdll.nccf_def_host_from_file(hostfile,
                                                  byref(self.hostId_ct))
        if status != 0:
            raise CDMSError("ERROR: not a valid host file %s (status=%d)" %
                            (hostfile, status))

        # Attach global attrs
        libcfdll.nccf_def_global_from_file(hostfile,
                                           byref(self.globalId_ct))

        # get the global attributes from the file
        natts = c_int(-1)
        attName_ct = c_char_p(" " * (libCFConfig.NC_MAX_NAME + 1))
        attValu_ct = c_char_p(" " * (libCFConfig.NC_MAX_NAME + 1))
        self.libcfdll.nccf_inq_global_natts(self.globalId_ct, byref(natts))
        for i in range(natts.value):
            self.libcfdll.nccf_inq_global_attval(self.globalId_ct,
                                                 i, attName_ct,
                                                 attValu_ct)
            if attName_ct.value not in self.attributes:
                self.attributes[attName_ct.value] = attValu_ct.value

        self.id = hostfile

        i_ct = c_int()
        status = libcfdll.nccf_inq_host_ngrids(self.hostId_ct, byref(i_ct))
        self.nGrids = i_ct.value
        status = libcfdll.nccf_inq_host_nstatdatafiles(self.hostId_ct,
                                                       byref(i_ct))
        self.nStatDataFiles = i_ct.value
        status = libcfdll.nccf_inq_host_ntimedatafiles(self.hostId_ct,
                                                       byref(i_ct))

        self.nTimeDataFiles = i_ct.value
        status = libcfdll.nccf_inq_host_ntimeslices(self.hostId_ct,
                                                    byref(i_ct))
        self.nTimeSliceFiles = i_ct.value

        fName_ct = c_char_p(" " * (libCFConfig.NC_MAX_NAME + 1))
        gName_ct = c_char_p(" " * (libCFConfig.NC_MAX_NAME + 1))

        self.dimensions = {"nGrids": self.nGrids,
                           "nStatDataFiles": self.nStatDataFiles,
                           "nTimeDataFiles": self.nTimeDataFiles,
                           "nTimeSliceFiles": self.nTimeSliceFiles}

        # Mosaic filename (use getMosaic to return the connectivity)
        mosaicFilename = c_char_p(" " * (libCFConfig.NC_MAX_NAME + 1))
        status = libcfdll.nccf_inq_host_mosaicfilename(self.hostId_ct,
                                                       mosaicFilename)
        self.mosaicFilename = mosaicFilename.value

        # Filenames
        timeFilenames = []
        statFilenames = []

        coordinates = []

        # static data
        for vfindx in range(self.nStatDataFiles):
            for gfindx in range(self.nGrids):
                status = libcfdll.nccf_inq_host_statfilename(self.hostId_ct,
                                                             vfindx, gfindx,
                                                             fName_ct)
                statFilenames.append(fName_ct.value)
                f = cdms2.open(fName_ct.value, 'r')
                varNames = f.listvariable()

                for vn in varNames:
                    # Add coordinate names a local list of coordinates
                    if 'coordinates' in dir(f[vn]):
                        for coord in f[vn].coordinates.split():
                            if coord not in coordinates:
                                coordinates.append(coord)
                    if vn not in self.statVars:
                        # allocate
                        self.statVars[vn] = ["" for ig in
                                             range(self.nGrids)]

                    # set file name
                    self.statVars[vn][gfindx] = fName_ct.value
                f.close()

        # time dependent data
        for vfindx in range(self.nTimeDataFiles):
            for tfindx in range(self.nTimeSliceFiles):
                for gfindx in range(self.nGrids):
                    status = \
                        libcfdll.nccf_inq_host_timefilename(self.hostId_ct,
                                                            vfindx,
                                                            tfindx,
                                                            gfindx,
                                                            fName_ct)
                    timeFilenames.append(fName_ct.value)
                    f = cdms2.open(fName_ct.value, 'r')
                    varNames = f.listvariable()
                    for vn in varNames:
                        # Add coordinate names a local list of coordinates
                        if 'coordinates' in dir(f[vn]):
                            for coord in f[vn].coordinates.split():
                                if coord not in coordinates:
                                    coordinates.append(coord)
                        if vn not in self.timeVars:
                            # allocate
                            self.timeVars[vn] = \
                                [["" for it in range(self.nTimeSliceFiles)]
                                 for ig in range(self.nGrids)]
                        # set file name
                        self.timeVars[vn][gfindx][tfindx] = fName_ct.value
                    f.close()

        # Grid names and data. Must come after time and static file dictionaries
        # because they define the coordinates.
        for gfindx in range(self.nGrids):
            status = libcfdll.nccf_inq_host_gridfilename(self.hostId_ct,
                                                         gfindx,
                                                         fName_ct)
            status = libcfdll.nccf_inq_host_gridname(self.hostId_ct,
                                                     gfindx,
                                                     gName_ct)

            varNames = cdms2.open(fName_ct.value, 'r').listvariable()
            for vn in varNames:
                if vn in coordinates:
                    if vn not in list(self.gridVars.keys()):
                        self.gridVars[vn] = []
                        self.gridName[vn] = []

                    self.gridVars[vn].append(fName_ct.value)
                    self.gridName[vn].append(gName_ct.value)

        # Populate the variables dictionary, avoid the grids
        self.variables = {}
        for item in list(self.statVars.keys()):
            self.variables[item] = StaticFileVariable(self, item)
        for item in list(self.timeVars.keys()):
            self.variables[item] = TimeFileVariable(self, item)

    def __initialize(self):
        """
        private method to inititialze the hostObj and for use in reseting
        the hostObj on close
        """

        self.mode = ''
        self.libcfdll = None
        self.uri = ''
        self.id = ''
        self._status_ = ''

        # ctypes variables
        self.hostId_ct = c_int(-1)
        self.globalId_ct = c_int(-1)

        # number of grid files
        self.nGrids = 0

        # number of static var files
        self.nStatDataFiles = 0

        # number of time dependent var files
        self.nTimeDataFiles = 0

        # number of time files
        self.nTimeSliceFiles = 0

        # {'varName': fileNames}
        # fileNames is array of ngrid
        self.gridVars = {}
        self.gridName = {}

        # {'varName': fileNames}
        # fileNames is array of ntimes x ngrid
        self.timeVars = {}

        # {'varName': fileNames}
        # fileNames is array of ngrid
        self.statVars = {}

        # global attributes
        self.attributes = {}

    def getMosaic(self):
        """
        Get the mosaic filename

        Returns
        -------
        mfn : Mosaic filename
        """
        from .gsMosaic import Mosaic
        mfn = Mosaic(self.mosaicFilename, "r")

        return mfn

    def getGridVarInfo(self):
        """
        Returns
        -------

             the dictionary associated with the grid containing grid names and files.
        """
        return self.gridVars

    def getGridFilenames(self):
        """
        Returns
        -------

             a list of time filenames. Assumes each coordinate is in each file.
        """
        c = list(self.gridVars.keys())
        return self.gridVars[c[0]]

    def getGridNames(self):
        """
        Returns
        -------

             a list of grid names
        """
        return list(self.gridName.values())

    def getStatFilenames(self, varName=None):
        """
                Get a list of static variable filenames

        Parameters
        ----------
                varName variable name (or None if all the static file names are to
        be returned)


        Returns
        -------

        list the file names corresponding to varName
        """
        if varName is not None:
            return self.statVars[varName]
        # return all the static var filenames
        return list(self.statVars.values())

    def getTimeFilenames(self, varName=None):
        """
        Get a list of time dependent variable filenames

        Parameters
        ----------
        varName : variable name. None for all variables

        Returns
        -------
        filename : for input variable name only

        """
        if varName is not None:
            return self.timeVars[varName]
        # return all the time var filenames
        return list(self.timeVars.values())

    def getCoordinates(self):
        """
        Coordinates variables contained within the host object

        Returns
        -------
        list of coordinate names
        """
        return list(self.gridVars.keys())

    def getNumGrids(self):
        """
        Get number of grids (tiles)

        Returns
        -------
        number of grids
        """
        c = list(self.gridVars.keys())
        return len(list(self.gridVars[c[0]].values()))

    def getNumStatDataFiles(self):
        """
        Get number of static data files

        Returns
        -------
        number static files
        """
        return self.nStatDataFiles

    def getNumTimeDataFiles(self):
        """
        Get number of time dependent data files

        Returns
        -------
        number time data files
        """
        return self.nTimeDataFiles

    def listvariable(self, gstype=None):
        """
        Get all variables

        Parameters
        ----------
        type Grid, Static, Time Dependent or None

        Returns
        -------
        list of all variables, including static and time dependent, Default = None
        """
        isNone = gstype is None
        isStr = isinstance(gstype, string_types)

        if isNone:
            variables = list(self.statVars.keys()) + list(self.timeVars.keys())
            return variables

        elif isStr:
            if gstype.upper() == "STATIC":
                return list(self.statVars.keys())
            if gstype[0:4].upper() == "TIME":
                return list(self.timeVars.keys())
            return None

        # Raise error
        else:
            text = 'type must be "Static", "Time", None or empty'
            raise CDMSError(text)

    def listvariables(self, type=None):
        """
        Synonymous to listvariable

        Parameters
        ----------
        type Grid, Static, Time Dependent or None

        Returns
        -------
        list of all variables, including static and time dependent
        """
        return self.listvariable(type)

    def listattribute(self, varName):
        """
        List the given variables attributes

        Parameters
        ----------
        varName variable name

        Returns
        -------
        attributes list
        """
        fName = ""
        if varName in self.statVars:
            fName = self.statVars[varName][0]
        elif varName in self.timeVars:
            fName = self.timeVars[varName][0][0]
        if fName:
            var = cdms2.open(fName, 'r')(varName)
            return var.listattributes()
        else:
            return []

    def listattributes(self, varName):
        """
        Synonymous to listattribute

        Parameters
        ----------
        varName variable name

        Returns
        -------
        attributes list
        """
        return self.listattribute(varName)

    def listdimension(self):
        """
        List a variable's dimensions

        Returns
        -------
        [nGrids, (n0, n1, ...)]
        """
        return list(self.dimensions.keys())

    def listglobal(self):
        """
        List global attributes of host file

        Returns
        -------
        a list of the global attributes in the file
        """
        return list(self.attributes.keys())

    def getglobal(self, attName):
        """
        Get the value of the global attribute

        Parameters
        ----------
        [attName] - global attribute name

        Returns
        -------
        attribute value
        """
        return self.attributes[attName]

    def listall(self, varName=None, all=None):
        """
        Get info about data from the file.

        Parameters
        ----------
        varName variable name

           * all include axes information

        Returns
        -------
        information about file.
        """

        if varName is None:
            return None
        var = self.getVariable(varName)
        return var.listall(all=all)

    def showall(self, varName=None, all=None, device=None):
        """
        Get info about data from the file.

        Paramenters
        -----------
        varName variable name

             * all include axes information

        Returns
        -------
        information about file.
        """
        import sys
        import string
        if device is None:
            device = sys.stdout
        if varName is None:
            return None
        var = self.getVariable(varName)
        alist = var.listall(all=all)
        device.write(string.join(alist, "\n"))
        device.write("\n")

    def close(self):
        """
        Close the file
        """
        self.__initialize()
        self._status_ = 'closed'

    def __repr__(self):
        """
        Python repr()

        Returns
        -------
        res Print statement
        """
        res = "< '%s',  URI: '%s', MODE: '%s', STATUS: '%s',\n libcf: %s >" % \
            (self.__class__, self.uri, self.mode,
              self._status_, self.libcfdll)
        return res

    def __del__(self):
        """
        Free the host file from memory
        """
        if self.hostId_ct.value >= 0:
            self.libcfdll.nccf_free_host(self.hostId_ct)
        self.hostId_ct.value = -1

# NOTE: There is no __call__ method for host files.

    def __getitem__(self, varName):
        """
        Get a variable by name

        Parameters
        ----------
        varName variable name

        Returns
        -------
        list of cdms2 file variables, one for each grid
        """
        # Static variables
        if varName in self.statVars:
            staticFV = StaticFileVariable(self, varName)
            return staticFV

        # Time variables
        elif varName in self.timeVars:
            timeVariables = TimeFileVariable(self, varName)
            return timeVariables

    def getVariable(self, varName):
        """
        Get a variable by name

        Parameters
        ----------
        varName variable name

        Returns
        -------
        list of cdms2 file variables, one for each grid
        """
        return self[varName]

    def getVariables(self):
        """
        Get all variables

        Returns
        -------
        list of file variables
        """
        statVars = [self[vn] for vn in self.statVars]
        timeVars = [self[vn] for vn in self.timeVars]
        return statVars + timeVars

    def getattribute(self, name):
        """
        Get the global attribute value by name

        Parameters
        ----------
        name attribute name

        Returns
        -------
        value
        """
        return self.attributes[name]

##############################################################################


def test():
    import sys
    """
    A path to the host file must be present. This also assumes that
    the data are in the same directory as the host file.
    """
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option("-f", "--file", dest="hostFilename",
                      help="host file name")

    options, args = parser.parse_args()
    if not options.hostFilename:
        print("""need to provide a host file, use -h
to get a full list of options""")
        sys.exit(1)

    print('open file..., create grdspec file object...')
    gf = cdms2.open(options.hostFilename)
    if gf._status_ == 'closed':
        print("File not opened")
        sys.exit(1)
    print()
    print("type=", type(gf))
    print('listvariable...')
    print(gf.listvariable())
    print('listattributes...')
    print(gf.listattribute('distance'))
    print(gf.listattribute('v'))
    print('listglobals...')
    print(gf.listglobal())
    print('print...')
    print(gf)
    print('access static data...', 'distance' in gf.listvariable())
    print(type(gf['distance']))
    di = gf['distance']
    print(di[0].size)
    print(gf['distance'][0].shape)
    print('acess time dependent data...', "V" in gf.listvariables())
    print(gf['V'][0].size)

    # Test the mosaic
    print('getMosaic...', 'getMosaic' in dir(gf))
    mosaic = gf.getMosaic()
    for c in mosaic.coordinate_names:
        print(c)
    for t in mosaic.tile_contacts:
        print("%s -> %s" % (t, mosaic.tile_contacts[t]))

##############################################################################


if __name__ == "__main__":
    test()

"""
File:       OpenSkySensor.py
Author:      Atilla Koksal
Last Update: 11/5/2018
Description: A GCCCD Software Sensor that retrieves and displays the current aircraft data
             from OpenSky Network API.  Bounding box which area cover a square area with
             about 14 miles on sides, which is nearly 7 miles on each direction Grossmont College
             campus is being the center of the square area.

"""
__version__ = "1.3"
__author__ = "Atilla Koksal"
__email__ = "atikoksal@yahoo.com"

from sensor import SensorX
import json
import os
import time
import logging
import errno
import requests
from datetime import datetime, timezone
from requests import Timeout, HTTPError, ConnectionError

class OpenSkySensor(SensorX):

    __LOG_DIRECTORY = 'OpenSkySensorLog'
    __LOG_FILENAME = 'OpenSkySensor.log'

    CONV_ALT = 3.281       # conversion factor - meter to feet
    CONV_SPD = 2.237       # conversion factor - convert m/s to miles/hr

    # dictionary to return the direction values when called with the get_trackdir function
    TRACK_LIST = {'0': 'North', '45': 'NorthEast', '90': 'East', '135': 'SouthEast', '180': 'South', '225': 'SouthWest',
                  '270': 'West', '315': 'NorthWest'}

    # Creates the log directory if it does not exist
    try:
        os.makedirs(os.path.join(os.path.dirname(__file__), __LOG_DIRECTORY))
    except OSError as e:
        if e.errno != errno.EEXIST:
            print("Error is: " + str(e))

    # Creates logging entries of the sensor data
    logging.basicConfig(
        level=logging.INFO,
        filename=os.path.join(os.path.dirname(__file__), __LOG_DIRECTORY, __LOG_FILENAME),
        filemode='a',
        format='%(asctime)s - %(lineno)d - %(levelname)s - %(message)s')

    def __init__(self):
        """ Creates a new OpenSkySensor objects and retrieves sensor settings """
        super().__init__(os.path.join(os.path.dirname(__file__), self.__class__.__name__))
        logging.info("Sensor  " + self.__class__.__name__ + " ready to be called")

    def has_updates(self, k):
        """ Returns updates if request is allowed based on aircraft icao24 id (k value) & there is content """
        if self._request_allowed():
            content = self._fetch_data()
            if 0 < len(content) and content[0]['k'] != k:
                return 1
        return 0

    def get_content(self, k):
        """ return content after k"""
        content = self.get_all()
        return content if 0 < len(content) and content[0]['k'] != k else None

    def get_all(self):
        """ return fresh or cached content"""
        if self._request_allowed():
            return self._fetch_data()
        else:
            return self._read_buffer()

    def _fetch_data(self):
        """ Retrieves the json encoded response from the OpenSky REST API"""
        try:
            response = requests.get(self.props['service_url'])
            self.props['last_used'] = int(time.time())
            self._save_settings()  # remember time of the last service request
            if response.status_code == 200 and response.json is not None:
                content = OpenSkySensor._create_content(response.json())
                logging.info("successfully requested new content")
                self._write_buffer(content)  # remember last service request(s) results.
            else:
                logging.warning("response: {} {} {}".format(response.status_code, response, response.text))
                content = None
        except (HTTPError, Timeout, ConnectionError, ValueError) as e:
            logging.error("except: " + str(e))
            content = None
        return content

    # overrides the method in SensorX
    # def _request_allowed(self):
    #     """ check if it's OK to call the 3rd party web-service again, or if we rather wait a little longer """
    #     print(int(time.time()) - self.props['last_used'])
    #     return not self.props['states'] or \
    #                (self.props['offline'] and int(time.time()) - self.props['last_used'] > self.props['request_delta'])

    @staticmethod
    def get_trackdir(f_track):
        """
        Returns the direction North, NorthEast, SouthEast, South, SouthWest, West, Northwest or North
        OpenSky API vector for track direction is 0 deg for true North, and clockwise for the rest.
        This function tries to find the compass directions assuming that 1 degree difference can be
        ignored
        """
        true_track = ''
        try:
            if f_track is "null" or f_track is None:
                return None

            for degree in sensor.TRACK_LIST:
                if (int(degree) - f_track) <= 1:
                    true_track = sensor.TRACK_LIST[degree]

                if (int(degree) > f_track) and (int(degree) - f_track) < 45:
                    true_track = sensor.TRACK_LIST[degree]
                else:
                    true_tract = sensor.TRACK_LIST['315']
            return true_track

        except (KeyError, ValueError, TypeError) as e:
            logging.error(e)
            return []

    @staticmethod
    def get_typeofaircraft(ft_dict):
        """ Retrieves the make and model of the aircraft from the json file if found.
            Data in the file was downloaded from OpenSky Network's website, and converted
            to json from csv format"""

        f_type = {}
        with open('Aircrafts.json') as code_list:
            codes = json.load(code_list)
            aircraft_mfc = ''
            aircraft_mod = ''

            for i in range(len(ft_dict)):
                for c in range(len(codes)):
                    if codes[c]['icao24'] == ft_dict['icao24']:
                        # type_dict['Manufacturer'] = (codes[c]['manufacturer'])
                        # type_dict.setdefault('Manufacturer', []).append(codes[c]['manufacturer'])
                        # type_dict.setdefault('Model', []).append(codes[c]['model'])
                        aircraft_mfc = codes[c]['manufacturer']
                        aircraft_mod = codes[c]['model']
                        break
                    else:
                        aircraft_mfc = 'Unidentified'
                        aircraft_mod = 'Unknown'
                f_type['Manufacturer'] = aircraft_mfc
                f_type['Model'] = aircraft_mod

                # if type_dict['Manufacturer'][i] is None:
                #   type_dict.setdefault('Manufacturer', []).append('Unidentified')

                # if type_dict['Manufacturer'][i] is {}:
                #   type_dict['Manufacturer'][i] = 'Unidentified'

            return f_type

    def get_featured_image(self):
        return os.path.join(os.path.dirname(__file__), 'images', self.props['featured_img'])


    @staticmethod
    def _create_content(fs_json):
        """ convert the json response from OpenSky REST API into some may be usefule information"""

        record = []
        f_list = []
        f_type = []

        try:
            if fs_json["states"] == "null" or fs_json["states"] is None:
                return None

            # get time from API, and convert to PST
            openSky_time = datetime.fromtimestamp(fs_json['time'], timezone.utc).astimezone()
            #curr_time = datetime.now()
            f_list = {}
            f_aircraft = {}

            # iterrates through the json list and copies the vectors into new dictionaries.
            for v in fs_json['states']:

                f_aircraft['icao24'] = v[0]
                f_list['Call no'] = v[1]
                f_list['Speed'] = v[9]
                f_list['TrackDir'] = v[10]
                f_list['VertRate'] = v[11]
                f_list['GeoAlt'] = v[13]
                f_list['CurrLong'] = v[5]
                f_list['CurrLat'] = v[6]

                # Gets the aircraft make and model from the function call
                f_type = OpenSkySensor.get_typeofaircraft(f_aircraft)

                f_aircraft['Vectors'] = f_list
                f_aircraft['Type'] = f_type

                aircraft_info = 'Aircraft is Manufactured by {} with Model No: {} '.format(
                    f_aircraft['Type']['Manufacturer'].upper(), f_aircraft['Type']['Model'].upper())

                vert_Pos = 'CLIMBING' if f_aircraft['Vectors']['VertRate'] > 0 else 'DESCENDING'

                aircraft_sum = 'It\'s cruising towards {} degrees, ({}) at {:.2f} ft. altitude with speed of {:.2f} '\
                               'mi/hr'.format(
                                (f_aircraft['Vectors']['TrackDir']),
                                OpenSkySensor.get_trackdir(f_aircraft['Vectors']['TrackDir']),
                                (f_aircraft['Vectors']['GeoAlt'] * sensor.CONV_ALT),
                                (f_aircraft['Vectors']['Speed'] * sensor.CONV_SPD))

                aircraft_vertPos = '. It\'s currently ' + vert_Pos + ' at the rate of {:0.2f} ft/s'.format(
                                                     f_aircraft['Vectors']['VertRate'] * sensor.CONV_ALT)

                f_out = {'k': f_aircraft['icao24'],
                         'date & time': 'Vectors retrieved on ' + openSky_time.strftime('%Y-%m-%d %I:%M:%S %p'),
                         'caption': aircraft_info,
                         'summary': aircraft_sum + aircraft_vertPos,
                         'img': os.path.join(os.path.dirname(__file__), 'images', sensor.props['background_img'])
                         }

                record.append(f_out)  # response is in a dictionary
            return record

        except (KeyError, ValueError, TypeError) as e:
            logging.error(e)
            return []

if __name__ == "__main__":
    """ Displays the flight/aircraft information. Some code from Roger Hinson's sensor """

    sensor = OpenSkySensor()
    print(str(sensor), ' is initialized...')
    flight_info = sensor.get_all()

    try:
        if flight_info is None:
            print('Currently there are NO flight vectors in the designated airspace or '
                  'air traffic data from sensors are not available')
        for flight in flight_info:
            print(flight)
    except (KeyError, ValueError, TypeError) as e:
        logging.error(e)

    print("\n\nRetrieving nearby flight updates...\n")

    time.sleep(15)  # Sleep/wait for 15 sec for updates

    n = 1
    if sensor.has_updates(n):
        flight_info = sensor.get_content(n)
        for flight in flight_info:
            print(flight)

    # try:
    #     if ft_dict is not TypeError:
    #         f_type = sensor.get_typeofaircraft()
    #         print(f_type.get())
    #     else:
    #         print(None)
    # except TypeError as e:
    #     print(e, "Data is Not available")

    # for i in range(3):
    #     ft_dict = sensor.get_all()
    #     print(ft_dict.get())
    #
    #     time.sleep(5)  # let's relax for short while
    #
    # n = 0
    # for i in range(60):
    #     if sensor.has_updates(n):
    #         f_new = sensor.get_content(n)  # list of dictionaries
    #         print(f_new.get())
    #
    #         n = f_new[0]['k']
    #     time.sleep(5)  # let's relax for short while
    #     print("sleeping ...")

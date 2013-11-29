#! /usr/bin/env python

# This script is designed to work inside a Transvision's folder
# (https://github.com/mozfr/transvision)

import collections
import glob
import json
import os
import re
import StringIO
from ConfigParser import SafeConfigParser
from optparse import OptionParser
from time import gmtime, strftime
from xml.dom import minidom

# Output detail level
# 0: print only actions performed and errors extracting data from searchplugins
# 1: print errors about missing list.txt and the complete Python's error message
outputlevel = 0




def extract_sp_product(path, product, locale, channel, jsondata, splist_enUS, html_output):
    global outputlevel
    try:
        if locale != "en-US":
            # Read the list of searchplugins from list.txt
            if (product != "metro"):
                sp_list = open(path + "list.txt", "r").read().splitlines()
            else:
                sp_list = open(path + "metrolist.txt", "r").read().splitlines()
            # Remove empty lines
            sp_list = filter(bool, sp_list)
            # Check for duplicates
            if (len(sp_list) != len(set(sp_list))):
                # set(sp_list) remove duplicates. If I'm here, there are
                # duplicated elements in list.txt, which is an error
                duplicated_items = [x for x, y in collections.Counter(sp_list).items() if y > 1]
                duplicated_items_str =  ", ".join(duplicated_items)
                html_output.append("<p><span class='error'>Error:</span> there are duplicated items (" + duplicated_items_str + ") in list.txt (" + locale + ", " + product + ", " + channel + ").</p>")

        else:
            # en-US is different: I must analyze all xml files in the folder,
            # since some searchplugins are not used in en-US but from other
            # locales
            sp_list = splist_enUS

        output = ""

        if locale != "en-US":
            # Get a list of all files inside path
            for singlefile in glob.glob(path+"*"):
                # Remove extension
                filename = os.path.basename(singlefile)
                filename_noext = os.path.splitext(filename)[0]
                if (filename_noext in splist_enUS):
                    # There's a problem: file exists but has the same name of an
                    # en-US searchplugin. Warn about this
                    html_output.append("<p><span class='error'>Error:</span> file " + filename + " should not exist in the locale folder, same name of en-US searchplugin (" + locale + ", " + product + ", " + channel + ").</p>")
                else:
                    # File is not in use, should be removed
                    if (filename_noext not in sp_list) & (filename != "list.txt") & (filename != "metrolist.txt"):
                        html_output.append("<p><span class='error'>Error:</span> file " + filename + " not in list.txt (" + locale + ", " + product + ", " + channel + ")")

        # For each searchplugin check if the file exists (localized version) or
        # not (using en-US version)
        for sp in sp_list:
            sp_file = path + sp + ".xml"

            existingfile = os.path.isfile(sp_file)

            if (locale != "en-US") & (sp in splist_enUS) & (existingfile):
                # There's a problem: file exists but has the same name of an
                # en-US searchplugin. This file will never be picked at build
                # time, so let's analyze en-US and use it for json, acting
                # like the file doesn't exist, and print an error
                existingfile = False

            if (existingfile):
                try:
                    searchplugin_info = "(" + locale + ", " + product + ", " + channel + ", " + sp + ".xml)"

                    try:
                        xmldoc = minidom.parse(sp_file)
                    except Exception as e:
                        # Some search plugin has preprocessing instructions
                        # (#define, #if), so they fail validation. In order to
                        # extract the information I need I read the file,
                        # remove lines starting with # and parse that content
                        # instead of the original XML file
                        preprocessor = False
                        newspcontent = ""
                        for line in open(sp_file, "r").readlines():
                            if re.match("#", line):
                                # Line starts with a #
                                preprocessor = True
                            else:
                                # Line is ok, adding it to newspcontent
                                newspcontent = newspcontent + line
                        if preprocessor:
                            html_output.append("<p><span class='warning'>Warning:</span> searchplugin contains preprocessor instructions (e.g. #define, #if) that have been stripped in order to parse the XML " + searchplugin_info + "</p>")
                            try:
                                xmldoc = minidom.parse(StringIO.StringIO(newspcontent))
                            except Exception as e:
                                html_output.append("<p><span class='error'>Error:</span> problem parsing XML for searchplugin " + searchplugin_info + "</p>")
                                if (outputlevel > 0):
                                    print e
                        else:
                            html_output.append("<p><span class='error'>Error:</span> problem parsing XML for searchplugin " + searchplugin_info + "</p>")
                            if (outputlevel > 0):
                                print e

                    # Some searchplugins use the form <tag>, others <os:tag>
                    try:
                        node = xmldoc.getElementsByTagName("ShortName")
                        if (len(node) == 0):
                            node = xmldoc.getElementsByTagName("os:ShortName")
                        name = node[0].childNodes[0].nodeValue
                    except Exception as e:
                        html_output.append("<p><span class='error'>Error:</span> problem extracting name from searchplugin " + searchplugin_info + "</p>")
                        name = "not available"

                    try:
                        node = xmldoc.getElementsByTagName("Description")
                        if (len(node) == 0):
                            node = xmldoc.getElementsByTagName("os:Description")
                        description = node[0].childNodes[0].nodeValue
                    except Exception as e:
                        # We don't really use description anywhere, so I don't print errors
                        description = "not available"

                    try:
                        # I can have more than one url element, for example one
                        # for searches and one for suggestions
                        secure = 0

                        nodes = xmldoc.getElementsByTagName("Url")
                        if (len(nodes) == 0):
                            nodes = xmldoc.getElementsByTagName("os:Url")
                        for node in nodes:
                            if node.attributes["type"].nodeValue == "text/html":
                                url = node.attributes["template"].nodeValue
                        p = re.compile("^https://")

                        if p.match(url):
                            secure = 1
                    except Exception as e:
                        html_output.append("<p><span class='error'>Error:</span> problem extracting url from searchplugin " + searchplugin_info + "</p>")
                        url = "not available"

                    try:
                        # Since bug 900137, searchplugins can have multiple images
                        images = []
                        nodes = xmldoc.getElementsByTagName("Image")
                        if (len(nodes) == 0):
                            nodes = xmldoc.getElementsByTagName("os:Image")
                        for node in nodes:
                            image = node.childNodes[0].nodeValue
                            images.append(image)

                            # On mobile we can't have % characters, see for example bug 850984. Print a warning in this case
                            if (product == "mobile"):
                                if ("%" in image):
                                    html_output.append("<p><span class='warning'>Warning:</span> searchplugin's image on mobile can't contain % character " + searchplugin_info + "</p>")

                    except Exception as e:
                        html_output.append("<p><span class='error'>Error:</span> problem extracting image from searchplugin " + searchplugin_info + "</p>")
                        images.append("data:image/x-icon;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAC/0lEQVR4XoWSbUiTexjG7x6d0OZW4FD3IigqaFEfJHRMt7WVGLQ9CZpR8pSiHwIZHHGdzbmzovl2tjnb8WjzBe2NCCnMFzycJ578kktwUZRDkCKhVDgouJdEn9n+/Sssy+Rc8Ptwc3FxX/z/NzQBwIBMxpsZHBx51d9fheddNeVwwHRLywV/b+/Yzfz8eMAixDicRVEPuBsbun1crkfR1FT5q/BTHI4EApQwPr53P0Inc8vLh27I5fHwyGKx+Lu60OvubuTF+Pr6WK/V+kOTKacTJs3mCn9rKzvndKL3PT1o0eOJ+qzWK8R/U1Pu8OLio/lgEDbX1mBvKMSJSUz05DU0fGkyabfD+srK+b0cTg8KhzkxsbHwMRRCywsLE3NerwuwwC2VcseNRtpnsyGmuRn9g/E6HCxjNFZjKp+YTOxkTQ2awb6/sTH6rL6e6UxP58F23dJo+KN1dfT9+npEWyzoMYax2SK0wcCOURSa0OvRc7M56jUYmNsajWArtwe26ZpYzE0rKXm4trpayBEKgWBZWF9aAi72eCkpKAowMTc8TOrn5z/AbhpQqfjXjh9/UScUotYjR9BfhYXoXnEx+levfzmgVAp+DhDbh/GGBoCEhNJ3s7MHgsvL8Mbng7fT0xAJhyGyuZklyM4+veudjJpM4CkpOX9RImGrANBn9ASBfo+JQUbM1YMH0ShFRUaqq3feyZDBAF0kWfGbWMwW4+AZTGVsbNSlVjN/HztGV3E46A8A1B4Xh9qzs9nbOt33O3lQWwsdJEmViURsKQ5SmDKCiLaqVEy3TCbokcv5nWo1fRm3qMWeFXNDJIrcJcmvTdpJsqwGh09iQ405jTe3KJWMSyr99s9tSUlcl0pFX8JNnADIjvkzOZm9c+rUWXBrtYpzaWmBMmxo8WazQsFcz83d8dqevDy+R6mkrbiJAQB1pKYGbmq1R7+YHTqdojwzc/VKfj7TJpHwYBc5ExO5bQUFtCMjI9i/Fd7CXVR0yJ6TI4D/kSMnh3/9xInDW/MnJPlM3rrfgeYAAAAASUVORK5CYII=")

                    # Check if node for locale already exists
                    if (locale not in jsondata):
                        jsondata[locale] = {}
                    # Check if node for locale->product already exists
                    if (product not in jsondata[locale]):
                        jsondata[locale][product] = {}
                    # Check if node for locale->product->channel already exists
                    if (channel not in jsondata[locale][product]):
                        jsondata[locale][product][channel] = {}

                    jsondata[locale][product][channel][sp] = {
                        "file": sp + ".xml",
                        "name": name,
                        "description": description,
                        "url": url,
                        "secure": secure,
                        "image": images,
                    }

                except Exception as e:
                    html_output.append("<p><span class='error'>Error:</span> problem analyzing searchplugin " + searchplugin_info + "</p>")
                    if (outputlevel > 0):
                        print e
            else:
                # File does not exists, locale is using the same plugin of en-
                # US, I have to retrieve it from the dictionary
                try:
                    searchplugin_enUS = jsondata["en-US"][product][channel][sp]

                    # Check if node for locale already exists
                    if (locale not in jsondata):
                        jsondata[locale] = {}
                    # Check if node for locale->product already exists
                    if (product not in jsondata[locale]):
                        jsondata[locale][product] = {}
                    # Check if node for locale->product->channel already exists
                    if (channel not in jsondata[locale][product]):
                        jsondata[locale][product][channel] = {}

                    jsondata[locale][product][channel][sp] = {
                        "file": sp + ".xml",
                        "name": searchplugin_enUS["name"],
                        "description": "(en-US) " + searchplugin_enUS["description"],
                        "url": searchplugin_enUS["url"],
                        "secure": searchplugin_enUS["secure"],
                        "image": searchplugin_enUS["image"]
                    }
                except Exception as e:
                    # File does not exist but we don't have the en-US either.
                    # This means that list.txt references a non existing
                    # plugin, which will cause the build to fail
                    html_output.append("<p><span class='error'>Error:</span> file referenced in list.txt but not available (" + locale + ", " + product + ", " + channel + ", " + sp + ".xml)</p>")
                    if (outputlevel > 0):
                        print e

    except Exception as e:
        if (outputlevel > 0):
            html_output.append("<p><span class='error'>Error:</span> problem reading  (" + locale + ")" + path + "list.txt</p>")




def extract_p12n_product(source, product, locale, channel, jsondata, html_output):
    global outputlevel

    # Use jsondata to create a list of all Searchplugins' descriptions
    try:
        available_searchplugins = []
        if (channel in jsondata[locale][product]):
            # I need to proceed only if I have searchplugin for this branch+product+locale
            for element in jsondata[locale][product][channel].values():
                if element["name"]:
                    available_searchplugins.append(element["name"])

            existingfile = os.path.isfile(source)
            if existingfile:
                try:
                    # Read region.properties, ignore comments and empty lines
                    values = {}
                    for line in open(source):
                        li = line.strip()
                        if (not li.startswith("#")) & (li != ""):
                            try:
                                # Split considering only the firs =
                                key, value = li.split('=', 1)
                                # Remove whitespaces, some locales use key = value instead of key=value
                                values[key.strip()] = value.strip()
                            except Exception as e:
                                html_output.append("<p><span class='error'>Error:</span> problem parsing " + source + " (" + locale + ", " + product + ", " + channel + ")</p>")
                                if (outputlevel > 0):
                                    print e
                except Exception as e:
                    html_output.append("<p><span class='error'>Error:</span> problem reading " + source + " (" + locale + ", " + product + ", " + channel + ")</p>")
                    if (outputlevel > 0):
                        print e

                # Check if node for locale already exists
                if (locale not in jsondata):
                    jsondata[locale] = {}
                # Check if node for locale->product already exists
                if (product not in jsondata[locale]):
                    jsondata[locale][product] = {}
                # Check if node for locale->product->channel already exists
                if (channel not in jsondata[locale][product]):
                    jsondata[locale][product][channel] = {}

                defaultenginename = '-'
                searchorder = {}
                feedhandlers = {}
                handlerversion = '-'
                contenthandlers = {}

                currentproductstring = '   [' + product + ', ' + channel + '] ';
                for key, value in values.iteritems():
                    lineok = False

                    # Default search engine name. Example:
                    # browser.search.defaultenginename=Google
                    if key.startswith('browser.search.defaultenginename'):
                        lineok = True
                        defaultenginename = values["browser.search.defaultenginename"]
                        if (unicode(defaultenginename, "utf-8") not in available_searchplugins):
                            html_output.append("<p><span class='error'>Error:</span> " + currentproductstring + " " + defaultenginename + " is set as default but not available in searchplugins (check if the name is spelled correctly)</p>")

                    # Search engines order. Example:
                    # browser.search.order.1=Google
                    if key.startswith('browser.search.order.'):
                        lineok = True
                        searchorder[key[-1:]] = value
                        if (unicode(value, "utf-8") not in available_searchplugins):
                            html_output.append("<p><span class='error'>Error:</span> " + currentproductstring + " " + value + " is defined in searchorder but not available in searchplugins (check if the name is spelled correctly)</p>")

                    # Feed handlers. Example:
                    # browser.contentHandlers.types.0.title=My Yahoo!
                    # browser.contentHandlers.types.0.uri=http://add.my.yahoo.com/rss?url=%s
                    if key.startswith('browser.contentHandlers.types.'):
                        lineok = True
                        if key.endswith('.title'):
                            feedhandler_number = key[-7:-6]
                            if (feedhandler_number not in feedhandlers):
                                feedhandlers[feedhandler_number] = {}
                            feedhandlers[feedhandler_number]["title"] = value
                            # Print warning for Google Reader
                            if (value.lower() == 'google'):
                                html_output.append("<p><span class='warning'>Warning:</span> " + currentproductstring + " Google Reader has been dismissed, see bug 882093 (" + key + ")</p>")
                        if key.endswith('.uri'):
                            feedhandler_number = key[-5:-4]
                            if (feedhandler_number not in feedhandlers):
                                feedhandlers[feedhandler_number] = {}
                            feedhandlers[feedhandler_number]["uri"] = value

                    # Handler version. Example:
                    # gecko.handlerService.defaultHandlersVersion=4
                    if key.startswith('gecko.handlerService.defaultHandlersVersion'):
                        lineok = True
                        handlerversion = values["gecko.handlerService.defaultHandlersVersion"]

                    # Service handlers. Example:
                    # gecko.handlerService.schemes.webcal.0.name=30 Boxes
                    # gecko.handlerService.schemes.webcal.0.uriTemplate=https://30boxes.com/external/widget?refer=ff&url=%s
                    if key.startswith('gecko.handlerService.schemes.'):
                        lineok = True
                        splittedkey = key.split('.')
                        ch_name = splittedkey[3]
                        ch_number = splittedkey[4]
                        ch_param = splittedkey[5]
                        if (ch_number not in contenthandlers):
                            contenthandlers[ch_number] = {}
                        if (ch_param == "name"):
                            contenthandlers[ch_number]["name"] = value
                        if (ch_param == "uriTemplate"):
                            contenthandlers[ch_number]["uri"] = value

                    # Ignore some keys for mail and seamonkey
                    if (product == "suite") or (product == "mail"):
                        ignored_keys = ['mail.addr_book.mapit_url.format', 'mailnews.messageid_browser.url', 'mailnews.localizedRe',
                                        'browser.translation.service', 'browser.search.defaulturl', 'browser.throbber.url',
                                        'startup.homepage_override_url', 'browser.startup.homepage', 'browser.translation.serviceDomain']
                        if key in ignored_keys:
                            lineok = True

                    # Unrecognized line, print warning
                    if (not lineok):
                        html_output.append("<p><span class='warning'>Warning:</span> unknown key in region.properties: " + locale + ", " + product + ", " + channel + "." + key + "=" + value + "</p>")

                try:
                    jsondata[locale][product][channel]["p12n"] = {
                        "defaultenginename": defaultenginename,
                        "searchorder": searchorder,
                        "feedhandlers": feedhandlers,
                        "handlerversion": handlerversion,
                        "contenthandlers": contenthandlers
                    }
                except Exception as e:
                    html_output.append("<p><span class='error'>Error:</span> problem saving data into json from " + source + " (" + locale + ", " + product + ", " + channel + ")</p>")

            else:
                if (outputlevel > 0):
                    html_output.append("<p><span class='warning'>Warning:</span> file does not exist " + source + " (" + locale + ", " + product + ", " + channel + ")</p>")
    except Exception as e:
        html_output.append("<p>[" + product + ', ' + channel + "] No searchplugins available for this locale</p>")



def p12n_differences (jsondata):

    def print_differences (more_stable, less_stable, more_stable_label, less_stable_label):
        diff = set(more_stable.keys()) - set(less_stable.keys())
        if diff:
            print "\nThere are differences between " + more_stable_label + " and " + less_stable_label + " for " + locale

            print "Items available in " + more_stable_label + " but non in " + less_stable_label
            for item in diff:
                print "  " + item

            temp_diff = set(less_stable.keys()) - set(more_stable.keys())
            if temp_diff:
                print "Items available in " + less_stable_label + " but non in " + more_stable_label
                for item in temp_diff:
                    print "  " + item

            common_items = set(more_stable.keys()).intersection(set(less_stable.keys()))
            if common_items:
                print "Items present in both but changed"
                for item in common_items:
                    if (more_stable[item] != less_stable[item]):
                        print "  " + item




    print "\n\n"
    print "**********************************************************************"
    print "*                       PRODUCTIZATION  CHECKS                       *"
    print "**********************************************************************"

    # Analyze Firefox
    for locale in jsondata:
        p12n_release = {}
        p12n_beta = {}
        p12n_aurora = {}
        p12n_trunk = {}

        if ("release" in jsondata[locale]["browser"]):
            p12n_release = jsondata[locale]["browser"]["release"]
        if ("beta" in jsondata[locale]["browser"]):
            p12n_beta = jsondata[locale]["browser"]["beta"]
        if ("aurora" in jsondata[locale]["browser"]):
            p12n_aurora = jsondata[locale]["browser"]["aurora"]
        if ("trunk" in jsondata[locale]["browser"]):
            p12n_trunk = jsondata[locale]["browser"]["trunk"]

        if (p12n_release and p12n_beta):
            print_differences (p12n_release, p12n_beta, "RELEASE", "BETA")

        if (p12n_beta and p12n_aurora):
            print_differences (p12n_beta, p12n_aurora, "BETA", "AURORA")

        if (p12n_aurora and p12n_trunk):
            print_differences (p12n_aurora, p12n_trunk, "AURORA", "TRUNK")



def extract_splist_enUS (pathsource, splist_enUS):
    # Create a list of en-US searchplugins in pathsource, store this data in
    # splist_enUS
    global outputlevel
    try:
        for singlefile in glob.glob(pathsource+"*.xml"):
            filename = os.path.basename(singlefile)
            filename_noext = os.path.splitext(filename)[0]
            splist_enUS.append(filename_noext)

    except Exception as e:
        print " Error: problem reading list of en-US searchplugins from " + pathsource
        if (outputlevel > 0):
            print e




def extract_p12n_channel(clproduct, pathsource, pathl10n, localeslist, channel, jsondata, clp12n, html_output):
    global outputlevel
    try:
        # Analyze en-US searchplugins
        html_output.append("<h2>Locale: <a id='en-US' href='#en-US'>en-US (" + channel.upper() + ")</a></h2>")
        path = pathsource + "COMMUN/"

        # Create a list of en-US searchplugins for each channel. If list.txt
        # for a locale contains a searchplugin with the same name of the en-US
        # one (e.g. "google"), this will have precedence. Therefore a file with
        # this name should not exist in the locale folder
        if (clproduct=="all") or (clproduct=="browser"):
            splistenUS_browser = []
            extract_splist_enUS(path + "browser/locales/en-US/en-US/searchplugins/", splistenUS_browser)
            extract_sp_product(path + "browser/locales/en-US/en-US/searchplugins/", "browser", "en-US", channel, jsondata, splistenUS_browser, html_output)
            # Metro: same searchplugins folder
            extract_sp_product(path + "browser/locales/en-US/en-US/searchplugins/", "metro", "en-US", channel, jsondata, splistenUS_browser, html_output)
            if clp12n:
                extract_p12n_product(path + "browser/locales/en-US/en-US/chrome/browser-region/region.properties", "browser", "en-US", channel, jsondata, html_output)

        if (clproduct=="all") or (clproduct=="mobile"):
            splistenUS_mobile = []
            extract_splist_enUS(path + "mobile/locales/en-US/en-US/searchplugins/", splistenUS_mobile)
            extract_sp_product(path + "mobile/locales/en-US/en-US/searchplugins/", "mobile", "en-US", channel, jsondata, splistenUS_mobile, html_output)
            if clp12n:
                extract_p12n_product(path + "mobile/locales/en-US/en-US/chrome/region.properties", "mobile", "en-US", channel, jsondata, html_output)

        if (clproduct=="all") or (clproduct=="mail"):
            splistenUS_mail = []
            extract_splist_enUS(path + "mail/locales/en-US/en-US/searchplugins/", splistenUS_mail)
            extract_sp_product(path + "mail/locales/en-US/en-US/searchplugins/", "mail", "en-US", channel, jsondata, splistenUS_mail, html_output)
            if clp12n:
                extract_p12n_product(path + "mail/locales/en-US/en-US/chrome/messenger-region/region.properties", "mail", "en-US", channel, jsondata, html_output)

        if (clproduct=="all") or (clproduct=="suite"):
            splistenUS_suite = []
            extract_splist_enUS(path + "suite/locales/en-US/en-US/searchplugins/", splistenUS_suite)
            extract_sp_product(path + "suite/locales/en-US/en-US/searchplugins/", "suite", "en-US", channel, jsondata, splistenUS_suite, html_output)
            if clp12n:
                extract_p12n_product(path + "suite/locales/en-US/en-US/chrome/browser/region.properties", "suite", "en-US", channel, jsondata, html_output)

        locale_list = open(localeslist, "r").read().splitlines()
        for locale in locale_list:
            html_output.append("<h2>Locale: <a id='" + locale + "' href='#" + locale + "'>" + locale + " (" + channel.upper() + ")</a></h2>")
            path = pathl10n + locale + "/"
            if (clproduct=="all") or (clproduct=="browser"):
                extract_sp_product(path + "browser/searchplugins/", "browser", locale, channel, jsondata, splistenUS_browser, html_output)
                if clp12n:
                    extract_p12n_product(path + "browser/chrome/browser-region/region.properties", "browser", locale, channel, jsondata, html_output)
            if (clproduct=="all") or (clproduct=="mobile"):
                extract_sp_product(path + "mobile/searchplugins/", "mobile", locale, channel, jsondata, splistenUS_mobile, html_output)
                if clp12n:
                    extract_p12n_product(path + "mobile/chrome/region.properties", "mobile", locale, channel, jsondata, html_output)
            if (clproduct=="all") or (clproduct=="mail"):
                extract_sp_product(path + "mail/searchplugins/", "mail", locale, channel, jsondata, splistenUS_mail, html_output)
                if clp12n:
                    extract_p12n_product(path + "mail/chrome/messenger-region/region.properties", "mail", locale, channel, jsondata, html_output)
            if (clproduct=="all") or (clproduct=="suite"):
                extract_sp_product(path + "suite/searchplugins/", "suite", locale, channel, jsondata, splistenUS_suite, html_output)
                if clp12n:
                    extract_p12n_product(path + "suite/chrome/browser/region.properties", "suite", locale, channel, jsondata, html_output)
    except Exception as e:
        print "Error reading list of locales from " + localeslist
        if (outputlevel > 0):
            print e




def main():

    # Parse command line options
    clparser = OptionParser()
    clparser.add_option("-p", "--product", help="Choose a specific product", choices=["browser", "mobile", "mail", "suite", "all"], default="all")
    clparser.add_option("-b", "--branch", help="Choose a specific branch", choices=["release", "beta", "aurora", "trunk", "all"], default="all")
    clparser.add_option("-s", "--productization", help="Enable productization checks", action="store_true")

    (options, args) = clparser.parse_args()
    clproduct = options.product
    clbranch = options.branch
    clp12n = options.productization if options.productization else False

    # Read configuration file
    parser = SafeConfigParser()
    parser.read("web/inc/config.ini")
    local_hg = parser.get("config", "local_hg")
    install_folder = parser.get("config", "install")

    # Set Transvision's folders and locale files
    release_l10n = local_hg + "/RELEASE_L10N/"
    beta_l10n = local_hg + "/BETA_L10N/"
    aurora_l10n = local_hg + "/AURORA_L10N/"
    trunk_l10n = local_hg + "/TRUNK_L10N/"

    release_source = local_hg + "/RELEASE_EN-US/"
    beta_source = local_hg + "/BETA_EN-US/"
    aurora_source = local_hg + "/AURORA_EN-US/"
    trunk_source = local_hg + "/TRUNK_EN-US/"

    trunk_locales = install_folder + "/central.txt"
    aurora_locales = install_folder + "/aurora.txt"
    beta_locales = install_folder + "/beta.txt"
    release_locales = install_folder + "/release.txt"

    jsonfilename = "web/searchplugins.json"
    jsondata = {}


    htmlfilename = "web/p12n.html"
    html_output = ['''<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset=utf-8>
            <title>p12n status</title>
            <style type="text/css">
                body {background-color: #FFF; font-family: Arial, Verdana; font-size: 14px; padding: 10px;}
                p {margin-top: 2px;}
                span.warning {color: orange; font-weight: bold;}
                span.error {color: red; font-weight: bold;}
                span.metro {color: blue; font-weight: bold;}
                span.code {font-family: monospace; font-size: 12px; background-color: #CCC;}
            </style>
        </head>

        <body>
        ''']
    html_output.append("<p>Last update: " + strftime("%Y-%m-%d %H:%M:%S", gmtime()) + "</p>")
    html_output.append("<p>Analyzing product: " + clproduct + "</p>")
    html_output.append("<p>Branch: " + clbranch + "</p>")

    if (clbranch=="all") or (clbranch=="release"):
        extract_p12n_channel(clproduct, release_source, release_l10n, release_locales, "release", jsondata, clp12n, html_output)
    if (clbranch=="all") or (clbranch=="beta"):
        extract_p12n_channel(clproduct, beta_source, beta_l10n, beta_locales, "beta", jsondata, clp12n, html_output)
    if (clbranch=="all") or (clbranch=="aurora"):
        extract_p12n_channel(clproduct, aurora_source, aurora_l10n, aurora_locales, "aurora", jsondata, clp12n, html_output)
    if (clbranch=="all") or (clbranch=="trunk"):
        extract_p12n_channel(clproduct, trunk_source, trunk_l10n, trunk_locales, "trunk", jsondata, clp12n, html_output)

    if (clbranch=="all") and (clp12n):
        p12n_differences(jsondata)

    # Write back updated json data
    jsonfile = open(jsonfilename, "w")
    jsonfile.write(json.dumps(jsondata, indent=4, sort_keys=True))
    jsonfile.close()

    # Finalize and write html
    html_output.append("</body>")
    html_code = "\n".join(html_output)
    html_file = open(htmlfilename, "w")
    html_file.write(html_code)
    html_file.close()




if __name__ == "__main__":
    main()

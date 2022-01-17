#!/bin/bash

# Usage:
#
#     cd data
#     ./import.sh username password
#
# Where 'username' and 'password' are your username and password for the
# Traveline National Dataset FTP server


# I think it's important that this goes before the `trap`
mkdir /var/lock/bustimes-import || {
    echo "An import appears to be running already"
    exit 1
}

function finish {
    rmdir /var/lock/bustimes-import 2> /dev/null
}
trap finish EXIT SIGINT SIGTERM

USERNAME=$1
PASSWORD=$2

function import_csv {
    # name of a zip archive:
    zip=$1
    # fragment of a Django management command name:
    cmd=$2
    # name of a CSV file contained in the zip archive:
    csv=$3

    unzip -oq "$zip" "$csv"
    ../../manage.py "import_$cmd" < "$csv"
}

mkdir -p NPTG/previous NaPTAN TNDS variations

cd NPTG
nptg_old=$(shasum nptg.ashx\?format=csv)
wget -qN https://naptan.app.dft.gov.uk/datarequest/nptg.ashx?format=csv
nptg_new=$(shasum nptg.ashx\?format=csv)

if [[ $nptg_old != "$nptg_new" ]]; then
    echo "NPTG"
    echo "  Importing regions"
    import_csv nptg.ashx\?format=csv regions Regions.csv
    echo "  Importing areas"
    import_csv nptg.ashx\?format=csv areas AdminAreas.csv
    echo "  Importing districts"
    import_csv nptg.ashx\?format=csv districts Districts.csv
    echo "  Importing localities"
    import_csv nptg.ashx\?format=csv localities Localities.csv
    echo "  Importing locality hierarchy"
    import_csv nptg.ashx\?format=csv adjacent_localities AdjacentLocality.csv
    echo "  Importing adjacent localities"
    import_csv nptg.ashx\?format=csv locality_hierarchy LocalityHierarchy.csv
fi


cd ..



ie_nptg_old=$(shasum NPTG_final.xml)
wget -qN https://www.transportforireland.ie/transitData/NPTG_final.xml
ie_nptg_new=$(shasum NPTG_final.xml)
if [[ "$ie_nptg_old" != "$ie_nptg_new" ]]; then
    echo "Irish NPTG"
    ../manage.py import_ie_nptg NPTG_final.xml
fi



cd NaPTAN
naptan_old=$(shasum naptan.zip)
../../manage.py update_naptan
naptan_new=$(shasum naptan.zip)

if [[ "$naptan_old" != "$naptan_new" ]]; then
    echo "NaPTAN"
    unzip -oq naptan.zip
fi

if compgen -G "*csv.zip" > /dev/null; then
    for file in *csv.zip; do
        unzip -oq "$file" Stops.csv StopAreas.csv StopsInArea.csv
        echo " $file"
        echo "  Stops"
        tr -d '\000' < Stops.csv | ../../manage.py import_stops && rm Stops.csv
        ../../manage.py correct_stops
        echo "  Stop areas"
        tr -d '\000' < StopAreas.csv | ../../manage.py import_stop_areas && rm StopAreas.csv
        echo "  Stops in area"
        tr -d '\000' < StopsInArea.csv | ../../manage.py import_stops_in_area || continue && rm StopsInArea.csv
        rm "$file"
    done
elif [ -f Stops.csv ]; then
    echo "  Stops"
    tr -d '\000' < Stops.csv | ../../manage.py import_stops && rm Stops.csv
    echo "  Stop areas"
    tr -d '\000' < StopAreas.csv | ../../manage.py import_stop_areas && rm StopAreas.csv
    echo "  Stops in area"
    tr -d '\000' < StopsInArea.csv | ../../manage.py import_stops_in_area && rm StopsInArea.csv
    echo "  Stops in area"
fi


cd ..

noc_old=$(ls -l NOC_DB.csv)
wget -qN https://mytraveline.info/NOC/NOC_DB.csv
noc_new=$(ls -l NOC_DB.csv)
if [[ $noc_old != $noc_new ]]; then
    wget -qN www.travelinedata.org.uk/noc/api/1.0/nocrecords.xml
    ../manage.py import_operators < NOC_DB.csv
    ../manage.py import_operator_contacts < nocrecords.xml
    ../manage.py correct_operators
fi

cd ..

if [[ $USERNAME == '' || $PASSWORD == '' ]]; then
   echo 'TNDS username and/or password not supplied :('
   exit 1
fi

./manage.py import_tnds "$USERNAME" "$PASSWORD"

./manage.py import_gtfs

finish

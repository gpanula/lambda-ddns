misc collection of python to be used as lamba functions

See route53-ddns.txt for the captured text from creating the function
and the required role & policy

## we are using the dnspython module for dns functions
## specifically cname & a record lookups when an instance is powered down

 dnspython --> http://www.dnspython.org/

 to use it with our lambda function, we need to package it up with
 the zip file we upload to AWS
 pip install dnspython -t /path/to/export/the/module
 that'll put the dnspython module in /path/to/export/the/module/dns
 we want to include the dns/ directory in our zip file
 zip -r union.py.zip union.py dns/

## update a funtion
aws lambda update-function-code --function-name ddns_lambda --zip-file fileb://union.py.zip --publish


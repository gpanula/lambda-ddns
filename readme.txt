misc collection of python to be used as lamba functions

See route53-ddns.txt for the captured text from creating the function
and the required role & policy

## update a funtion
aws lambda update-function-code --function-name ddns_lambda --zip-file fileb://union.py.zip --publish


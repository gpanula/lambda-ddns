import json
import boto3
import re
import uuid
import time
import random
from datetime import datetime

print('Loading function ' + datetime.now().time().isoformat())
route53 = boto3.client('route53')
ec2 = boto3.resource('ec2')
compute = boto3.client('ec2')
dynamodb_client = boto3.client('dynamodb')
dynamodb_resource = boto3.resource('dynamodb')

#################################################################
### Defining our functions                                   ####
### Most these copied from
### https://github.com/awslabs/aws-lambda-ddns-function/blob/master/union.py
#################################################################

def get_zone_id(zone_name):
    """This function returns the zone id for the zone name that's passed into the function."""
    if zone_name[-1] != '.':
        zone_name = zone_name + '.'
    hosted_zones = route53.list_hosted_zones()
    x = filter(lambda record: record['Name'] == zone_name, hosted_zones['HostedZones'])
    try:
        zone_id_long = x[0]['Id']
        zone_id = str.split(str(zone_id_long),'/')[2]
        return zone_id
    except:
        return None

def create_resource_record(zone_id, host_name, hosted_zone_name, type, value):
    """This function creates resource records in the hosted zone passed by the calling function."""
    print 'Updating %s record %s in zone %s ' % (type, host_name, hosted_zone_name)
    if host_name[-1] != '.':
        host_name = host_name + '.'
    route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    "Comment": "Updated by Lambda DDNS",
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": host_name + hosted_zone_name,
                                "Type": type,
                                "TTL": 60,
                                "ResourceRecords": [
                                    {
                                        "Value": value
                                    },
                                ]
                            }
                        },
                    ]
                }
            )

def delete_resource_record(zone_id, host_name, hosted_zone_name, type, value):
    """This function deletes resource records from the hosted zone passed by the calling function."""
    print 'Deleting %s record %s in zone %s' % (type, host_name, hosted_zone_name)
    if host_name[-1] != '.':
        host_name = host_name + '.'
    route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    "Comment": "Updated by Lambda DDNS",
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": host_name + hosted_zone_name,
                                "Type": type,
                                "TTL": 60,
                                "ResourceRecords": [
                                    {
                                        "Value": value
                                    },
                                ]
                            }
                        },
                    ]
                }
            )




#################################################################
### Defining some defaults                                   ####
#################################################################

# default subdomain
# This the domain where A records will get registered
default_subdomain = "aws"

# default root domain
root_domain = "imednet.com"

# default_subdomain + root_domain
# is the default location to register A records in
default_zone = "%s.%s" % (default_subdomain, root_domain)



#################################################################
### Useful references                                        ####
#################################################################

## http://boto3.readthedocs.io/en/latest/
## http://stackoverflow.com/questions/15286401/print-multiple-arguments-in-python

## get list of running instances
## http://boto3.readthedocs.io/en/latest/guide/migrationec2.html#checking-what-instances-are-running

## original blog article that me started
## https://aws.amazon.com/blogs/compute/building-a-dynamic-dns-for-route-53-using-cloudwatch-events-and-lambda/

## code for the function in the blog article
## https://github.com/awslabs/aws-lambda-ddns-function

################################################################
### Running Code                                            ####
################################################################
instances = ec2.instances.filter(
    Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])

for instance in instances:
    print 'instance id %s ' % instance.id
    for tag in instance.tags:
        if 'zone' in tag.get('Key',{}):
            # set this to force where A & CNAME records will be registered
            zone = tag.get('Value').lstrip().lower()
            print 'zone is %s ' % zone
        if 'Name' in tag.get('Key',{}):
            # this is used in the creation of the A record
            name = tag.get('Value').lstrip().lower()
            print 'name is %s ' % name
        if 'imednet-env' in tag.get('Key',{}):
            # target env is where the CNAME records will get registered
            # e.g. memcache.automation-rc-aws.imednet.com
            target_env = tag.get('Value').lstrip().lower()
            print 'target_env environment is %s ' % target_env
        if 'function' in tag.get('Key',{}):
            # function is used to build a useful CNAME
            # e.g. shard-0.automation-rc-aws.imednet.com
            function = tag.get('Value').lstrip().lower()
            print 'VM function is %s ' % function
        if 'cname' in tag.get('Key',{}):
            # you force the CNAME by simply specifying it in the cname tag
            cname = tag.get('Value').lstrip().lower()
            print 'CName is %s ' % cname
        if 'root_domain' in tag.get('Key',{}):
            root_domain = tag.get('Value').lstrip().lower()

    # we have finished looping thru the tags

    # Here's how we will build records
    # A record is name.default_zone
    # CNAME is function.target_env.root_domain and points to name.default_zone

    # now we check if a specific zone was given
    # it'll error out if zone isn't defined
    try:
        # a zone was specified, so we'll registered everything in that zone
        default_zone = zone
    except:
        print 'Custom zone not defined'
        try:
            zone = "%s.%s" % (target_env, root_domain)
        except:
            print 'target_env not defined, using default_zone'
            zone = default_zone


    default_zone_id = get_zone_id(default_zone)
    zone_id = get_zone_id(zone)

    print ''
    print 'Dynamically built dns entries are'
    a_name = "%s.%s" % (name, default_zone)
    if not instance.public_ip_address:
        # host is not externally accessible aka no public name or ip address
        print 'No public ip address found'
        print("Attempting to create A record for  {}.{} A {}".format(name, default_zone, instance.private_ip_address))
        try:
            create_resource_record(default_zone_id, name, default_zone, 'A', instance.private_ip_address)
        except BaseException as e:
            print e
        
        print("Attempting to create CNAME record for  {}.{} CNAME {}.{}".format(function, zone, name, default_zone))
        try:
            create_resource_record(zone_id, function, zone, 'CNAME', a_name)
        except BaseException as e:
            print e
    else:
        # host is externally accessible aka has public name and ip address
        print 'Found public ip address of %s' % instance.public_ip_address
        print("Attempting to create A record for {}.{} A {}".format(name, default_zone, instance.public_ip_address))
        try:
            create_resource_record(default_zone_id,name, default_zone, 'A', instance.public_ip_address)
        except BaseException as e:
            print e

        print("Attempting to create CNAME record for {}.{} CNAME {}".format(function, zone, instance.public_dns_name))
        try:
            create_resource_record(zone_id, function, zone, 'CNAME', instance.public_dns_name)
        except BaseException as e:
            print e


    ### Now we deal with reverse lookup stuff
    
    print(instance.id, instance.instance_type, instance.private_ip_address, instance.private_dns_name, instance.public_dns_name, instance.public_ip_address )
    for goo in instance.tags:
        print(goo)


    ### Now we deal with reverse lookup stuff


print ''
print('Completed function ' + datetime.now().time().isoformat())
print ''



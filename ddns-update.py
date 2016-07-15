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


## One function to delete or create
## just tell the function what action(create or delete) we want
def modify_resource_record(zone_id, host_name, hosted_zone_name, type, value, action):
    """This function creates or deletes resource records in the hosted zone passed by the calling function."""
    if action == 'create':
        print 'Updating %s record %s in zone %s ' % (type, host_name, hosted_zone_name)
        action = 'UPSERT'
    elif action == 'delete':
        print 'Deleting %s record %s in zone %s' % (type, host_name, hosted_zone_name)
        action = 'DELETE'
    else:
        print 'Uknown action %s ' % (action)
        return
    if host_name[-1] != '.':
        host_name = host_name + '.'
    route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    "Comment": "Updated by Lambda DDNS",
                    "Changes": [
                        {
                            "Action": action,
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


# reverse lookup functions
def reverse_list(list):
    """Reverses the order of the instance's IP address and helps construct the reverse lookup zone name."""
    if (re.search('\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}',list)) or (re.search('\d{1,3}.\d{1,3}.\d{1,3}\.',list)) or (re.search('\d{1,3}.\d{1,3}\.',list)) or (re.search('\d{1,3}\.',list)):
        list = str.split(str(list),'.')
        list = filter(None, list)
        list.reverse()
        reversed_list = ''
        for item in list:
            reversed_list = reversed_list + item + '.'
        return reversed_list
    else:
        print 'Not a valid ip'
        exit()

def get_reversed_domain_prefix(subnet_mask, private_ip):
    """Uses the mask to get the zone prefix for the reverse lookup zone"""
    if 32 >= subnet_mask >= 24:
        third_octet = re.search('\d{1,3}.\d{1,3}.\d{1,3}.',private_ip)
        return third_octet.group(0)
    elif 24 > subnet_mask >= 16:
        second_octet = re.search('\d{1,3}.\d{1,3}.', private_ip)
        return second_octet.group(0)
    else:
        first_octet = re.search('\d{1,3}.', private_ip)
        return first_octet.group(0)

def create_reverse_lookup_zone(instance, reversed_domain_prefix, region):
    """Creates the reverse lookup zone."""
    print 'Creating reverse lookup zone %s' % reversed_domain_prefix + 'in.addr.arpa.'
    route53.create_hosted_zone(
        Name = reversed_domain_prefix + 'in-addr.arpa.',
        VPC = {
            'VPCRegion':region,
            'VPCId': instance['Reservations'][0]['Instances'][0]['VpcId']
        },
        CallerReference=str(uuid.uuid1()),
        HostedZoneConfig={
            'Comment': 'Updated by Lambda DDNS',
        },
    )

def get_hosted_zone_properties(zone_id):
    hosted_zone_properties = route53.get_hosted_zone(Id=zone_id)
    hosted_zone_properties.pop('ResponseMetadata')
    return hosted_zone_properties


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

# Our list of Route53 hosted domains
hosted_zones = route53.list_hosted_zones()

instances = ec2.instances.filter(
    Filters=[{'Name': 'instance-state-name', 'Values': ['stopped', 'running']}])


for instance in instances:
    print ''
    print '##################################################################################'
    print '###################     instance id %s                 ###################' % instance.id
    print '##################################################################################'
    for tag in instance.tags:
        if 'override_zone' in tag.get('Key',{}):
            # set this to force where A & CNAME records will be registered
            override_zone = tag.get('Value').lstrip().lower()
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
        print 'Setting default_zone to match override_zone tag of %s' % override_zone
        default_zone = override_zone
    except:
        print 'Custom zone not defined'
        try:
            print 'Setting vmzone to %s.%s' % (target_env, root_domain)
            vmzone = "%s.%s" % (target_env, root_domain)
        except:
            print 'target_env not defined, using default_zone'
            vmzone = default_zone


    # we need zone ids so we can update them
    # if can't get zone ids, then we just bail out here
    try:
        default_zone_id = get_zone_id(default_zone)
        zone_id = get_zone_id(vmzone)
    except BaseException as e:
        print('Failed to retrieve zone ids.\n')
        print(e)
        exit()

    # if no function, then default to name
    try:
        # and in case something has multiple fuctions
        # define the tag function with a space seperate list of functions
        funlist = function.split(' ')
    except:
        function = name
        funlist = function.split(' ')

    # make sure we have a name
    try:
        # now some really quick santizing of the Name
        name = name.split('.')[0]
        name = name.split(' ')[0]
    except:
        name = instance.id

    print ''
    fullname = "%s.%s" % (name, default_zone)
    print('Fullname is %s ' % (fullname))
    print '' 
    

    # grab the state of the instance
    # NOTE: later we'll get info from the cloudwatch event
    state = instance.state.get('Name', {})

    if state == 'running':
        mod_action = 'create'
    else:
        mod_action = 'delete'

    # reverse lookup bits
    # Get the subnet mask of the instance
    #subnet_id = instance['Reservations'][0]['Instances'][0]['SubnetId']
    # this might break if the instance has multiple subnets
    subnet = ec2.Subnet(instance.subnet_id)
    cidr_block = subnet.cidr_block
    subnet_mask = int(cidr_block.split('/')[-1])

    reversed_ip_address = reverse_list(instance.private_ip_address)
    reversed_domain_prefix = get_reversed_domain_prefix(subnet_mask, instance.private_ip_address)
    reversed_domain_prefix = reverse_list(reversed_domain_prefix)

    # Set the reverse lookup zone
    reversed_lookup_zone = reversed_domain_prefix + 'in-addr.arpa.'
    print 'The reverse lookup zone for this instance is:', reversed_lookup_zone


    vpc_id = instance.vpc_id

    # Now we make sure the reverse lookup zone exists and is associated
    if filter(lambda record: record['Name'] == reversed_lookup_zone, hosted_zones['HostedZones']):
        print 'Reverse lookup zone found:', reversed_lookup_zone
        reverse_lookup_zone_id = get_zone_id(reversed_lookup_zone)
        reverse_hosted_zone_properties = get_hosted_zone_properties(reverse_lookup_zone_id)
        if vpc_id in map(lambda x: x['VPCId'], reverse_hosted_zone_properties['VPCs']):
            print 'Reverse lookup zone %s is associated with VPC %s' % (reverse_lookup_zone_id, vpc_id)
        else:
            print 'Associating zone %s with VPC %s' % (reverse_lookup_zone_id, vpc_id)
            try:
                associate_zone(reverse_lookup_zone_id, region, vpc_id)
            except BaseException as e:
                print e
    else:
        print 'No matching reverse lookup zone'
        # create private hosted zone for reverse lookups
        if state == 'running':
            create_reverse_lookup_zone(instance, reversed_domain_prefix, region)
            reverse_lookup_zone_id = get_zone_id(reversed_lookup_zone)


    print ''
    a_name = "%s.%s" % (name, default_zone)
    if not instance.public_ip_address:
        # host is not externally accessible aka no public name or ip address
        print 'No public ip address found'
        #print("Attempting to remove A record for  {}.{} A {}".format(name, default_zone, instance.private_ip_address))
        try:
            modify_resource_record(default_zone_id, name, default_zone, 'A', instance.private_ip_address, mod_action)
            modify_resource_record(reverse_lookup_zone_id, reversed_ip_address, 'in-addr.arpa', 'PTR', fullname, mod_action)
        except BaseException as e:
            print e
       
        for fun in funlist:
            #print("Attempting to remove CNAME record for  {}.{} CNAME {}.{}".format(fun, vmzone, name, default_zone))
            try:
                modify_resource_record(zone_id, fun, vmzone, 'CNAME', a_name, mod_action)
            except BaseException as e:
                print e
    else:
        # host is externally accessible aka has public name and ip address
        print 'Found public ip address of %s' % instance.public_ip_address
        #print("Attempting to remove A record for {}.{} A {}".format(name, default_zone, instance.public_ip_address))
        try:
            modify_resource_record(default_zone_id, name, default_zone, 'A', instance.public_ip_address, mod_action)
            modify_resource_record(reverse_lookup_zone_id, reversed_ip_address, 'in-addr.arpa', 'PTR', fullname, mod_action)
        except BaseException as e:
            print e

        for fun in funlist:
            #print("Attempting to remove CNAME record for {}.{} CNAME {}".format(fun, vmzone, instance.public_dns_name))
            try:
                modify_resource_record(zone_id, fun, vmzone, 'CNAME', instance.public_dns_name, mod_action)
            except BaseException as e:
                print e


    ### Now we deal with reverse lookup stuff
   
    print '' 
    print(instance.id, instance.instance_type, instance.state, instance.private_ip_address, instance.private_dns_name, instance.public_dns_name, instance.public_ip_address )
    for goo in instance.tags:
        print(goo)

    print '##################################################################################'
    print ''


print ''
print('Completed function ' + datetime.now().time().isoformat())
print '##################################################################################'
print ''



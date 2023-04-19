from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from .models import *
from datetime import date


#used for write operations (post/put)
class WriteRouteSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField()
    group = serializers.PrimaryKeyRelatedField()

    class Meta:
        model = Route
        fields = ['title', 'description', 'verified', 'public', 'startingPointLat', 'startingPointLon', 'user', 'group']

    # Only one and exactly one of the two nullable fields (group, user) can be null at a time.
    def validate(self, data):
        user = data.get('user')
        group = data.get('group')
        if (user is not None and group is not None) or (user is None and group is None):
            raise serializers.ValidationError("Only one of user and group can be specified")
        return data

# read-only, nestable serializer
class SmallGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['name']

# nested in 'SmallMemberSerializer'
class SmallUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

# used in 'LargeUserSerializer' and 'LargeGroupSerializer'
class ExtraSmallRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = ['title', 'description']


# class IsWithinSerializer(serializers.ModelSerializer):
#     attraction = SmallAttractionSerializer()
    
#     class Meta:
#         model = isWithin
#         fields = ['orderNumber', 'attraction']

# retreives ALL the information for a a route
class LargeRouteSerializer(serializers.ModelSerializer):
    author = SmallUserSerializer()
    is_within = IsWithinSerializer(many=True) # one for each attraction of the route
    group = SmallGroupSerializer()

    class Meta:
        model = Route
        fields = ['title', 'description', 'verified', 'public', 'startingPointLat', 'startingPointLon', 'publicationDate',
                  'author', 'is_within', 'group']
        
# used in 'LargeMemberSerializer' and 'WriteMemberSerializer'
class LargeUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']

# retrieves partial information about a route
class SmallRouteSerializer(serializers.ModelSerializer):
    author = SmallUserSerializer()
    group = SmallGroupSerializer()

    class Meta:
        model = Route
        fields = ['title', 'description', 'verified', 'author', 'group']

class RegisterUserSerializer(serializers.ModelSerializer):
    passwordCheck = serializers.CharField(style={'input_type': 'password'}, write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password', 'passwordCheck', 'first_name', 'last_name', 'email']
        extra_kwargs = {'passwordCheck': {'write_only': True}}

    # custom save method logic, to accommodate password 
    # matching and properly setting the validated password
    def save(self, **kwargs):
        password = self.validated_data['password']
        passwordCheck = self.validated_data['passwordCheck']

        # the two passwords fields must match
        if password != passwordCheck:
            raise serializers.ValidationError({'password': 'Passwords must match!'})
        
        # email can be neither null, nor blank
        if self.validated_data.get('email') is None or self.validated_data['email'] == '':
            raise serializers.ValidationError({'email': 'Email field is required.'})

        # creating instance of User Model
        user = User(username=self.validated_data['username'], 
                    # first and last names can be blank
                    first_name=self.validated_data.pop('first_name', ''), 
                    last_name=self.validated_data.pop('last_name', ''),
                    email=self.validated_data.pop('email'))
        
        # properly setting the password
        user.set_password(password)
        user.save()
        return user


# a regular Serializer is used, so that no 'create'-related validations or
# any other default behaviour of a ModelSerializer pollute the POST request
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(label='Username', write_only=True)
    password = serializers.CharField(label='Password', style={'input_type': 'password'}, trim_whitespace=False, write_only=True)

    def validate(self, attrs):      # overwritten
        username = attrs['username']
        password = attrs['password']

        if not username or not password:
            raise serializers.ValidationError({'authorization': 'Both "username" and "password" are required!'})
        
        # using the built-in django method for authentication
        user = authenticate(request=self.context['request'], username=username, password=password)

        if not user:
            raise serializers.ValidationError({'authorization': 'Invalid username or password!'})
        
        # the user is properly validated, which means it can be 
        # placed in the serializer's validated_data attribute
        attrs['user'] = user
        return attrs


class ChangePasswordSerializer(serializers.ModelSerializer):
    newPassword = serializers.CharField(style={'input_type': 'password'}, write_only=True)

    class Meta:
        model = User
        fields = ['password', 'newPassword']

    # custom update method for password checking and newPassword validation
    def update(self, instance, validated_data):
        password = validated_data['password']
        updatedPassword = validated_data['newPassword']

        # make sure provided current password is valid
        if not check_password(password, instance.password):
            raise serializers.ValidationError({'password': 'Incorrect password.'})

        # validate provided new password
        try:
            validate_password(updatedPassword)
        except Exception as invalidPassword:
            raise serializers.ValidationError({'newPassword': invalidPassword})

        instance.set_password(updatedPassword)
        instance.save()
        return instance

# status serializer
class StatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = Status
        fields = ['status']
        
# shows minimum of information, used when displaying all entries in a list
class SmallNotebookSerializer(serializers.ModelSerializer):

    status = StatusSerializer()
    class Meta:
        model = Notebook
        fields = ['title', 'note', 'status']


# read-only, nestable serializer
class SmallMemberSerializer(serializers.ModelSerializer):
    baseUser = SmallUserSerializer(read_only=True)

    class Meta:
        model = Member
        fields = ['baseUser', 'profilePhoto', 'birthDate']

# used for put/patch/delete on the Member model
class WriteMemberSerializer(serializers.ModelSerializer):
    baseUser = LargeUserSerializer()

    class Meta:
        model = Member
        fields = ['baseUser', 'profilePhoto', 'birthDate']

    # custom update method, for updating the related user
    # with the corresponding validated data, before updating
    # their associated member
    def update(self, instance, validated_data):
        # extract validated user data
        extractedUserData = validated_data.pop('baseUser', None)

        if extractedUserData:
            # aquire instance
            currentBaseUser = instance.baseUser
            # serialize and verify the validated user data
            currentBaseUserSerializer = LargeUserSerializer(currentBaseUser, data=extractedUserData, partial=True)
            currentBaseUserSerializer.is_valid(raise_exception=True)
            # save the changes
            currentBaseUserSerializer.save()
        
        # update the member itself
        return super().update(instance, validated_data)


class RegisterMemberSerializer(serializers.ModelSerializer):
    baseUser = RegisterUserSerializer()

    class Meta:
        model = Member
        fields = ['baseUser', 'profilePhoto', 'birthDate']

    # custom save method, so that a baseUser can be instantiated
    # before the Member instance itself;
    def save(self, **kwargs):
        baseUserData = self.validated_data['baseUser']
        # creating serializer based on validated data
        baseUserSerializer = RegisterUserSerializer(data=baseUserData)
        # validating said data
        baseUserSerializer.is_valid(raise_exception=True)
        # creating the instance
        baseUser = baseUserSerializer.save()

        member = Member(
            baseUser=baseUser,
            profilePhoto=self.validated_data.pop('profilePhoto', None),
            birthDate=self.validated_data['birthDate']
        )

        member.save()
        return member


# used for post/put/patch/delete on the Group model
class WriteGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['name', 'description']


# retrieves minimal information about an attraction, for queries with
# minimal requirements
class SmallAtractionSerializer(serializers.ModelSerializer):
    tag = SmallTagSerializer()

    class Meta:
        model = Attraction
        fields = ['name', 'generalDescription', 'tag']

# small flag serializer, gives minimal information about rating
class SmallRatingFlagSerializer(serializers.ModelSerializer):

    route = ExtraSmallRouteSerializer()
    attraction = SmallAtractionSerializer()

    class Meta:
        model = Rating
        fields = ['rating', 'comment', 'route', 'attraction']

# large flag serializer, gives detailed information about rating
class LargeRatingFlagSerializer(serializers.ModelSerializer):

    user = SmallUserSerializer()
    route = ExtraSmallRouteSerializer()
    attraction = SmallAtractionSerializer()

    class Meta:
        model = Rating
        fields = ['user', 'rating', 'comment', 'route', 'attraction']

# retrieves ALL the information about an attraction
class LargeAttractionSerializer(serializers.ModelSerializer):
    images = ImageSerializer(many=True)
    tag = SmallTagSerializer()
    ratings = SmallRatingFlagSerializer(source='filtered_ratings', many=True)

    class Meta:
        model = Attraction
        fields = ['name', 'generalDescription', 'latitude', 'longitude', 'images', 'tag', 'ratings']

##### BelongsTo #####
#####################

class WriteBelongsToSerializer(serializers.ModelSerializer):
    member = serializers.PrimaryKeyRelatedField()
    group = serializers.PrimaryKeyRelatedField()

    class Meta:
        model = BelongsTo
        fields = ['member', 'group', 'isAdmin', 'nickname']


class GroupBelongsToSerializer(serializers.ModelSerializer):
    groups = SmallGroupSerializer(many=True, read_only=True)
    
    class Meta:
        model = BelongsTo
        fields = ['groups', 'isAdmin', 'nickname']


class MemberBelongsToSerializer(serializers.ModelSerializer):
    member = SmallMemberSerializer(many=True, read_only=True)

    class Meta:
        model = BelongsTo
        fields = ['member', 'isAdmin', 'nickname']

class LargeMemberSerializer(serializers.ModelSerializer):
    baseUser = LargeUserSerializer(read_only=True)
    groups = GroupBelongsToSerializer(many=True, read_only=True)
    routes = ExtraSmallRouteSerializer(many=True, read_only=True)
    ratings = SmallRatingFlagSerializer(many=True, read_only=True)  
    notebooks = SmallNotebookSerializer(many=True, read_only=True)

    class Meta:
        model = Member
        fields = ['baseUser', 'profilePhoto', 'birthdate', 'groups', 'routes', 'ratings', 'notebooks']

# shows everything it is to know about a specific notebook-entry
class LargeNotebookSerializer(serializers.ModelSerializer):

    route = SmallRouteSerializer()
    user = SmallMemberSerializer()
    status = StatusSerializer()


    class Meta:
        model = Notebook
        fields = ['title', 'note', 'dateStarted', 'status', 'dateCompleted', 'user']

# used to display only the fields necessary when put / post requests are made
class WriteNotebookSerializer(serializers.ModelSerializer):
    
    # using a custom create function as I need to make a few modifications
    # before saving the object in the database
    def create(self, validated_data):
        request = self.context.get('request')

        # if the user making the request is authenticated
        if request and request.user.is_authenticated:

            member = Member.objects.get(baseUser=request.user)
            # they become the user of the current notebook-entry, note that the member object was added
            validated_data['user'] = member
            # the starting date of the current entry becomes today's date
            validated_data['dateStarted'] = date.today()

            # if the user sets the status as 'Completed' upon creation
            if validated_data['status'].status == "Completed":
                # then the Completed date also becomes today's date
                validated_data['dateCompleted'] = date.today()
        else:
            raise serializers.ValidationError({'user': 'You must be logged in to perform this action.'})
        
        # if there are no modifications made regarding: dateCompleted -> it remains null 
        # calling parent class function to perform better validation of data
        return super().create(validated_data)

    # same goes for update
    def update(self, instance, validated_data):
        request = self.context.get('request')

        if request and request.user.is_authenticated:
            member = Member.objects.get(baseUser=request.user)
            validated_data['user'] = member
            # the previous status
            old_status = instance.status.status

            # the user wants to change the status of the trip
            # it changes it from anything (including 'Completed') to 'Completed'
            if validated_data['status'].status == 'Completed':
                # then the completion date also changes
                validated_data['dateCompleted'] = date.today()
            
            # it changes it from 'Completed' to anything (including 'Completed')
            elif old_status == 'Completed':
                # the completion date becomes null
                validated_data['dateCompleted'] = None
                # the starting date is also modified
                validated_data['dateStarted'] = date.today()
        else:
            raise serializers.ValidationError({'user': 'You must be logged in to perform this action.'})
        # calling parent class function to perform better validation of data
        return super().update(instance, validated_data)
    
    class Meta:
        model = Notebook
        fields = ['route', 'title', 'note', 'status']

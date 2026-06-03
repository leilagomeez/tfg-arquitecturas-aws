const { SQSClient, ReceiveMessageCommand, DeleteMessageCommand } = require("@aws-sdk/client-sqs");
const cacheTtlInSec = 300;
const memcached = require('../cache/memcache');

let config = {
    VISIBILITY_TIMEOUT_IN_SEC: 5,
    LONG_POLL_WAIT_IN_SEC: 5,
}

Object.keys(config).forEach(key => {
    if (process.env[key] === undefined) {
        console.log(`[NOTICE] Value for key '${key}' not found in ENV, using default value.`)
    } else {
        config[key] = process.env[key]
    }
});

const sqs_url = get_sqs_endpoint();

module.exports = bean_model => {
    if (sqs_url) {
        const region = parse_region_from_endpoint(sqs_url);
        const sqs = new SQSClient({ region });
        console.log("Listening to SQS:", sqs_url);
        read_message(sqs, bean_model);
    } else {
        console.log("No env var: SQS_ENDPOINT seen. Not listening to SQS");
    }
}

async function read_message(sqs, bean_model) {
    try {
        const data = await sqs.send(new ReceiveMessageCommand({
            QueueUrl: sqs_url,
            MaxNumberOfMessages: 1,
            VisibilityTimeout: parseInt(config.VISIBILITY_TIMEOUT_IN_SEC),
            WaitTimeSeconds: parseInt(config.LONG_POLL_WAIT_IN_SEC)
        }));

        if (!data || !data.Messages || data.Messages.length === 0) {
            console.log('Nothing to process');
            read_message(sqs, bean_model);
        } else {
            await update_db(data, sqs, bean_model);
        }
    } catch (err) {
        console.log("Error receiving message:", err);
        read_message(sqs, bean_model);
    }
}

function get_sqs_endpoint() {
    if (process.env["SQS_ENDPOINT"] === undefined) {
        console.log("SQS endpoint not found");
        return false;
    }
    return process.env["SQS_ENDPOINT"];
}

async function update_db(sqs_data, sqs, bean_model) {
    const bean_attributes = parse_message(sqs_data.Messages[0]);
    const receipt_handle = sqs_data.Messages[0].ReceiptHandle;

    bean_model.getBeanBySupplierIdType(
        bean_attributes.supplier_id,
        bean_attributes.bean_type,
        async (err, bean) => {
            if (err) {
                console.log("Error retrieving bean:", err);
                read_message(sqs, bean_model);
            } else {
                bean.quantity = Number(bean_attributes.quantity) + Number(bean.quantity);
                bean_model.updateById(bean.id, bean, async (err, data) => {
                    if (err) {
                        console.log("Error updating bean quantity:", err);
                        read_message(sqs, bean_model);
                    } else {
                        await delete_item_from_sqs(sqs, receipt_handle);
                        clear_cache(bean);
                        read_message(sqs, bean_model);
                    }
                });
            }
        }
    );
}

function parse_region_from_endpoint(endpoint) {
    const re = /sqs\.([a-z0-9-]+)/;
    const match = endpoint.match(re);
    return match[1];
}

async function delete_item_from_sqs(sqs, receipt_handle) {
    try {
        await sqs.send(new DeleteMessageCommand({
            QueueUrl: sqs_url,
            ReceiptHandle: receipt_handle
        }));
        console.log('Successfully deleted message from queue');
    } catch (err) {
        console.log("Error deleting message:", err);
    }
}

function clear_cache(bean) {
    memcached.set('beans_' + bean.id, JSON.stringify(bean), cacheTtlInSec, function(err) {
        if (err) console.error("Unable to clear cache for bean:", bean.id, err);
        else console.log("Cleared cache for bean:", bean.id);
    });
    memcached.del('beans_all', function(err) {
        if (err) console.error("Unable to clear 'beans_all' cache:", err);
        else console.log("Cleared cache for 'beans_all'");
    });
}

function parse_message(message_item) {
    const message_body = JSON.parse(message_item.Body);
    const message = message_body.Message;
    console.log("SQS message field:", message);
    const message_segments = message.split(':').map(e => e.trim());
    const fields = {
        supplier_id: message_segments[0],
        bean_type: message_segments[1],
        quantity: message_segments[2]
    };
    console.log("SQS message parsed as:", fields);
    return fields;
}
